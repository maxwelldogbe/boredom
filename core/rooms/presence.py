"""Presence half of the room manager: room:event pushes, offline notices, offline forfeits.

Mixed into RoomManager. Scheduling methods expect the caller to hold `room.lock`; the
timer tasks take the lock themselves.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from rooms.models_types import Player, Room

logger = logging.getLogger("rooms.presence")


class PresenceMixin:
    """Requires the RoomManager attributes (and GameFlowMixin's `_forfeit`)."""

    rooms: dict[str, Room]
    clock: Callable[[], float]
    send: Callable[[str, dict[str, Any]], Awaitable[None]]
    offline_notice_ms: float
    offline_forfeit_ms: float

    async def _room_event(
        self, room: Room, kind: str, player: Player, data: dict[str, Any] | None = None
    ) -> None:
        """Push a transient `room:event` to everyone online. Never replayed on reconnect."""
        event: dict[str, Any] = {"kind": kind, "playerId": player.id, "nickname": player.nickname}
        if data is not None:
            event["data"] = data
        await self._push(room, {"type": "room:event", "data": event})

    # ----- offline notice -----------------------------------------------------------------

    def _schedule_offline_notice(self, room: Room, player: Player) -> None:
        """Announce player_offline only if they are still offline after the notice delay."""
        self._cancel_notice(room, player.id)
        since = player.offline_since
        room.notice_tasks[player.id] = asyncio.create_task(
            self._offline_notice(room, player.id, since)
        )

    async def _offline_notice(self, room: Room, player_id: str, since: float | None) -> None:
        await asyncio.sleep(self.offline_notice_ms / 1000)
        async with room.lock:
            if room.notice_tasks.get(player_id) is not asyncio.current_task():
                return
            room.notice_tasks.pop(player_id, None)
            player = room.player(player_id)
            if self.rooms.get(room.code) is not room or player is None:
                return
            if player.online or player.left or player.offline_since != since:
                return
            player.offline_notified = True
            await self._room_event(room, "player_offline", player)

    async def _back_online(self, room: Room, player: Player) -> None:
        """A seat was reclaimed: stop its offline timers; say so if its absence was announced."""
        self._cancel_notice(room, player.id)
        self._cancel_forfeit(room, player.id)
        if player.offline_notified:
            player.offline_notified = False
            await self._room_event(room, "player_online", player)

    def _cancel_notice(self, room: Room, player_id: str) -> None:
        task = room.notice_tasks.pop(player_id, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    # ----- offline forfeit ----------------------------------------------------------------

    def _schedule_forfeit(self, room: Room, player: Player) -> None:
        """Forfeit an in-game player still offline OFFLINE_FORFEIT_MS after disconnecting.

        The clock starts at the disconnect, or at the game start if they were already offline.
        """
        if room.status != "playing" or player.online or not player.in_game:
            return
        if player.id not in room.game_players:
            return
        self._cancel_forfeit(room, player.id)
        start = max(player.offline_since or self.clock(), room.game_started_at or 0.0)
        delay = max(0.0, (start + self.offline_forfeit_ms - self.clock()) / 1000)
        room.forfeit_tasks[player.id] = asyncio.create_task(
            self._offline_forfeit(room, player.id, delay)
        )

    async def _offline_forfeit(self, room: Room, player_id: str, delay: float) -> None:
        await asyncio.sleep(delay)
        async with room.lock:
            if room.forfeit_tasks.get(player_id) is not asyncio.current_task():
                return
            room.forfeit_tasks.pop(player_id, None)
            player = room.player(player_id)
            if self.rooms.get(room.code) is not room or room.status != "playing":
                return
            if player is None or player.online or not player.in_game:
                return
            try:
                await self._forfeit(room, player, "offline")
                await self._broadcast_room(room)
            except Exception:
                logger.exception("Offline forfeit failed in room %s", room.code)

    def _cancel_forfeit(self, room: Room, player_id: str) -> None:
        task = room.forfeit_tasks.pop(player_id, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()
