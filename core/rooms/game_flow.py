"""Game half of the room manager: start, actions, presence, timers, finish.

Mixed into RoomManager. Every method here expects the caller to hold `room.lock`,
except the timer task, which takes the lock itself.
"""

import asyncio
import copy
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from games import registry
from games.base import GameError, GameEvent, GameModule
from games.constants import SESSION_POINTS_MAX
from games.scoring import score_results
from rooms import hooks
from rooms.models_types import Room, RoomError, result_to_public

logger = logging.getLogger("rooms.game_flow")


class GameFlowMixin:
    """Runs the selected game module for a room. Requires the RoomManager attributes."""

    rooms: dict[str, Room]
    clock: Callable[[], float]
    send: Callable[[str, dict[str, Any]], Awaitable[None]]

    def _module(self, room: Room) -> GameModule:
        """The module of the game currently running in `room`."""
        module = registry.get_game(room.game_id or "")
        if module is None:
            raise RoomError("INVALID_ACTION", "No game is running.")
        return module

    async def _start_game(self, room: Room) -> None:
        """Initialise the selected game for every seated player and broadcast."""
        module = registry.get_game(room.selected_game or "")
        if module is None:
            raise RoomError("INVALID_ACTION", "Select a game first.")
        seated = room.seated()
        if not module.min_players <= len(seated) <= module.max_players:
            raise RoomError(
                "INVALID_ACTION",
                f"{module.name} needs {module.min_players} to {module.max_players} players.",
            )
        now = self.clock()
        try:
            state = module.init([p.id for p in seated], dict(room.settings), self._rng(), now)
        except GameError as exc:
            raise RoomError(exc.code, exc.message) from None
        events: list[GameEvent] = []
        for player in seated:
            if not player.online:
                state, extra = module.on_presence(state, player.id, False, now)
                events.extend(extra)
        room.game_id = module.id
        room.status = "playing"
        room.game_started_at = now
        hooks.on_game_started(room.code, module.id)
        await self._broadcast_room(room)
        await self._apply(room, state, events)

    async def _game_action(
        self, room: Room, player_id: str, action: dict[str, Any], allow: Callable[[], bool]
    ) -> None:
        """Validation order: status playing, rate limit, module. Nothing changes on error."""
        if room.status != "playing":
            raise RoomError("INVALID_ACTION", "No game is running.")
        if not allow():
            raise RoomError("RATE_LIMITED", "Slow down a little.")
        module = self._module(room)
        try:
            state, events = module.handle_action(
                copy.deepcopy(room.game_state), player_id, action, self.clock()
            )
        except GameError as exc:
            raise RoomError(exc.code, exc.message) from None
        await self._apply(room, state, events)

    async def _presence_changed(self, room: Room, player_id: str, online: bool) -> None:
        """Tell the running game a player went offline or came back."""
        if room.status != "playing":
            return
        module = self._module(room)
        state, events = module.on_presence(
            copy.deepcopy(room.game_state), player_id, online, self.clock()
        )
        await self._apply(room, state, events)

    async def _apply(self, room: Room, state: Any, events: list[GameEvent]) -> None:
        """Store new game state, send views and events, then finish or reschedule."""
        module = self._module(room)
        room.game_state = state
        room.last_activity = self.clock()
        await self._send_views(room, module)
        for event in events:
            await self._push(room, {"type": "game:event", "data": event})
        if module.is_over(state):
            await self._finish(room, module)
        else:
            self._reschedule(room, module)

    async def _send_views(self, room: Room, module: GameModule) -> None:
        """Send each online player their own view."""
        server_now = self.clock()
        for player in room.players:
            if player.online and player.channel:
                view = module.get_view(room.game_state, player.id)
                message = {
                    "type": "game:view",
                    "data": {"gameId": module.id, "view": view, "serverNow": server_now},
                }
                await self.send(player.channel, {"type": "push", "message": message})

    async def _finish(self, room: Room, module: GameModule) -> None:
        """Record results on the scoreboard, announce them and drop players who left."""
        self._cancel_timer(room)
        results = score_results(module.get_results(room.game_state), SESSION_POINTS_MAX)
        finished = hooks.game_record(room, module.id, self.clock(), results)
        for result in results:
            pid = result["player_id"]
            room.scoreboard[pid] = round(room.scoreboard.get(pid, 0) + result["points"], 2)
            if result["placement"] == 1:
                room.wins[pid] = room.wins.get(pid, 0) + 1
        room.status = "finished"
        public = [result_to_public(r) for r in results]
        await self._push(
            room,
            {"type": "game:event", "data": {"kind": "gameOver", "data": {"results": public}}},
        )
        for player in [p for p in room.players if p.left]:
            room.players.remove(player)
            room.scoreboard.pop(player.id, None)
            room.wins.pop(player.id, None)
        await self._broadcast_room(room)
        try:
            hooks.on_game_finished(finished)
        except Exception:
            logger.exception("Game-finished hook failed: room=%s game=%s", room.code, module.id)

    def _cancel_timer(self, room: Room) -> None:
        """Cancel the room's pending game timer, unless it is the task running now."""
        task = room.timer_task
        room.timer_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    def _reschedule(self, room: Room, module: GameModule) -> None:
        """Keep exactly one timer per room, set for the module's earliest deadline."""
        self._cancel_timer(room)
        deadline = module.next_deadline(room.game_state)
        if deadline is None:
            return
        delay = max(0.0, (deadline - self.clock()) / 1000)
        room.timer_task = asyncio.create_task(self._timer(room, delay))

    async def _timer(self, room: Room, delay: float) -> None:
        """Sleep until the deadline, then tick the game under the room lock."""
        await asyncio.sleep(delay)
        async with room.lock:
            if room.timer_task is not asyncio.current_task():
                return
            room.timer_task = None
            if self.rooms.get(room.code) is not room or room.status != "playing":
                return
            try:
                module = self._module(room)
                state, events = module.tick(copy.deepcopy(room.game_state), self.clock())
                await self._apply(room, state, events)
            except Exception:
                logger.exception("Game tick failed in room %s", room.code)
