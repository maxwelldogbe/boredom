"""Solo half of the room manager: solo rooms (one player and a bot), the bot driver, records.

Mixed into RoomManager. A solo room is private: only its owner reaches it again (by roomToken
or account); room:join from anyone else, room:peek, invites and spectating never see it. It
skips the lobby, ready check, reactions and offline forfeit, and closes after SOLO_IDLE_TTL_MS
with nobody connected. A finished game updates only the owner's SoloRecord and writes the
solo_started / solo_finished events: never the scoreboard, PlayerStats, analytics sessions,
recent players or the guest quota.

The bot moves through the same `_game_action` path as a player. After every state change
`_drive_bot` schedules at most one task for the bot's turn, tied to `room.bot_seq`; the task
waits a think time, computes the move off the event loop (bots/), then acts only if nothing
changed meanwhile.
"""

import asyncio
import logging
import random
import secrets
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any

from analytics.recorder import recorder
from bots import CHOOSERS
from brag.services import BragStore
from games import availability
from games.base import GameError
from games.constants import PLAYER_COLORS, SOLO_DIFFICULTIES
from games.solo_match import is_challenge, solo_module_for
from rooms.models_types import Player, Profile, Room, RoomError
from solo.services import SoloRecordStore

logger = logging.getLogger("rooms.solo")

DEFAULT_DIFFICULTY = "medium"
BOT_NICKNAME = "Bot"


DOTS = "dots_and_boxes"
DOTS_SIZES = (4, 5, 6)
DEFAULT_DOTS_SIZE = 5


CHALLENGE_OPTIONS: dict[str, dict[str, Any]] = {  # challenge variant keys and defaults
    "guess_race": {"content": "mixed"},
    "name_it": {"topic": "random"},
    "hangman": {},
}


def _variant(game_id: str, variant: Any) -> dict[str, Any]:
    """A solo:start variant, validated with defaults: {difficulty} (and size for Dots) for a
    bot game; {content}, {topic} or {} for a challenge (checked again by its module)."""
    if variant is None:
        variant = {}
    if game_id in CHALLENGE_OPTIONS:
        defaults = CHALLENGE_OPTIONS[game_id]
        if not isinstance(variant, dict) or set(variant) - set(defaults):
            raise RoomError("INVALID_ACTION", "Unknown solo option.")
        return {**defaults, **variant}
    allowed = {"difficulty", "size"} if game_id == DOTS else {"difficulty"}
    if not isinstance(variant, dict) or set(variant) - allowed:
        raise RoomError("INVALID_ACTION", "Unknown solo option.")
    difficulty = variant.get("difficulty", DEFAULT_DIFFICULTY)
    if difficulty not in SOLO_DIFFICULTIES:
        raise RoomError("INVALID_ACTION", "Pick easy, medium or hard.")
    if game_id != DOTS:
        return {"difficulty": difficulty}
    size = variant.get("size", DEFAULT_DOTS_SIZE)
    if type(size) is not int or size not in DOTS_SIZES:
        raise RoomError("INVALID_ACTION", "Pick a 4x4, 5x5 or 6x6 board.")
    return {"difficulty": difficulty, "size": size}


def _record_variant(game_id: str, variant: dict[str, Any]) -> str:
    """The SoloRecord variant: the difficulty, or "<difficulty>:<size>x<size>" for Dots; for a
    challenge the content type, the topic (as played) or "classic" for hangman."""
    if game_id == "guess_race":
        return variant["content"]
    if game_id == "name_it":
        return variant["topic"]
    if game_id == "hangman":
        return "classic"
    if game_id == DOTS:
        return f"{variant['difficulty']}:{variant['size']}x{variant['size']}"
    return variant["difficulty"]


class SoloMixin:
    """Requires the RoomManager attributes and the GameFlow/Upkeep mixins."""

    rooms: dict[str, Room]
    clock: Callable[[], float]
    send: Callable[[str, dict[str, Any]], Awaitable[None]]
    solo_idle_ms: float
    bot_think_ms: tuple[float, float]
    bot_continue_ms: tuple[float, float]
    bot_budget_ms: float
    bot_slots: asyncio.Semaphore
    solo_store: SoloRecordStore
    brag_store: BragStore

    def _solo_room_of(self, user_id: int) -> Room | None:
        return next((r for r in self.rooms.values() if r.solo and r.solo_owner == user_id), None)

    # ----- requests ----------------------------------------------------------------------

    async def solo_start(
        self, channel: str, profile: Profile, game_id: Any, variant: Any
    ) -> dict[str, Any]:
        """A new solo room with the sender (and a bot, for a bot game); the game starts at once.

        The account's previous solo room is closed first, with nothing recorded.
        """
        if profile.user_id is None:
            raise RoomError("REGISTERED_ONLY", "Solo games are for registered players.")
        module = solo_module_for(game_id) if isinstance(game_id, str) else None
        if module is None:
            raise RoomError("INVALID_ACTION", "This game can't be played alone.")
        chosen = _variant(game_id, variant)
        if is_challenge(module):
            try:
                module.validate_settings(chosen)
            except GameError as exc:
                raise RoomError(exc.code, exc.message) from None
        await availability.ensure_loaded()
        if not availability.is_enabled(game_id):
            raise RoomError("GAME_DISABLED", "This game is turned off right now.")
        old = self._solo_room_of(profile.user_id)
        if old is not None:
            async with old.lock:
                if self.rooms.get(old.code) is old:
                    await self._delete_room(old)
        now = self.clock()
        room = Room(
            code=self._new_code(),
            host_id="",
            created_at=now,
            last_activity=now,
            solo=True,
            solo_owner=profile.user_id,
            solo_variant=chosen,
            bot_rng=self._rng(),
        )
        self.rooms[room.code] = room
        async with room.lock:
            player = self._new_player(room, profile, channel)
            room.players.append(player)
            if not is_challenge(module):
                bot = Player(
                    id="b_" + secrets.token_hex(6),
                    profile_id="",
                    nickname=BOT_NICKNAME,
                    color=next(c for c in reversed(PLAYER_COLORS) if c != player.color),
                    avatar=None,
                    joined_at=now,
                    token="",
                    bot=True,
                )
                room.players.append(bot)
            room.host_id, room.selected_game = player.id, game_id
            await self._begin_solo_game(room, module, None)
            return {"code": room.code, **self._seat_reply(room, player)}

    async def solo_again(self, code: str | None, player_id: str | None) -> None:
        """A new game (or run) in the finished solo room, same variant; in a bot game the first
        mover alternates."""
        room = self._room(code)
        async with room.lock:
            player = self._solo_owner_seat(room, player_id)
            if room.status == "playing":
                raise RoomError("GAME_IN_PROGRESS", "A game is still in progress.")
            module = solo_module_for(room.selected_game or "")
            if module is None:
                raise RoomError("INVALID_ACTION", "This game can't be played alone.")
            if is_challenge(module):
                await self._begin_solo_game(room, module, None)
                return
            bot = room.bot()
            if bot is None:
                raise RoomError("INVALID_ACTION", "This game can't be played alone.")
            first = bot.id if room.solo_first == player.id else player.id
            await self._begin_solo_game(room, module, first)

    async def solo_quit(self, code: str | None, player_id: str | None) -> None:
        """Close the solo room. Nothing is recorded."""
        room = self._room(code)
        async with room.lock:
            self._solo_owner_seat(room, player_id)
            await self._close_solo(room)

    def _solo_owner_seat(self, room: Room, player_id: str | None) -> Player:
        player = self._member(room, player_id)
        if not room.solo or player.user_id != room.solo_owner:
            raise RoomError("INVALID_ACTION", "You are not in a solo game.")
        return player

    async def _close_solo(self, room: Room) -> None:
        """Delete a solo room at its owner's request (no detach message for their socket)."""
        for player in room.players:
            player.channel = None
        await self._delete_room(room)

    # ----- games -------------------------------------------------------------------------

    async def _begin_solo_game(self, room: Room, module: Any, first: str | None) -> None:
        player, bot = room.players[0], room.bot()
        now = self.clock()
        if is_challenge(module):
            settings: dict[str, Any] = dict(room.solo_variant)
            seats = [player.id]
        else:
            assert bot is not None
            settings = {"firstMover": first} if first else {}
            if "size" in room.solo_variant:
                settings["size"] = room.solo_variant["size"]
            seats = [player.id, bot.id]
        state = module.init(seats, settings, self._rng(), now)
        room.game_id, room.status, room.game_started_at = module.id, "playing", now
        room.game_players, room.forfeits, room.end_reason = seats, {}, None
        room.solo_first = None if is_challenge(module) else module.first_mover(state)
        room.solo_result = None
        room.last_activity = now
        for seat in room.players:
            seat.in_game = True
        game_id = room.selected_game or module.id
        if is_challenge(module):
            meta = {"game_id": game_id, "variant": self._solo_variant_of(room, module, state)}
        else:
            meta = {"game_id": game_id, "difficulty": room.solo_variant.get("difficulty")}
        recorder.record_event("solo_started", user_id=room.solo_owner, game_id=game_id, meta=meta)
        await self._broadcast_room(room)
        await self._apply(room, state, [])

    @staticmethod
    def _solo_variant_of(room: Room, module: Any, state: Any) -> str:
        """The SoloRecord variant of the game in play (a random Name It topic as played)."""
        if hasattr(module, "variant"):
            return module.variant(state)
        return _record_variant(room.selected_game or module.id, room.solo_variant)

    async def _solo_finish(self, room: Room, module: Any, reason: str) -> None:
        """Called by `_finish`: the SoloRecord, the solo_finished event and soloResult only."""
        if is_challenge(module):
            await self._challenge_finish(room, module, reason)
            return
        self._end_game_timers(room)
        now = self.clock()
        owner = room.players[0]
        outcome = module.outcome(room.game_state, owner.id)
        room.status, room.end_reason = "finished", reason
        difficulty = room.solo_variant.get("difficulty", "")
        variant = _record_variant(room.selected_game or module.id, room.solo_variant)
        record = None
        if room.solo_owner is not None:
            record = await self.solo_store.record(room.solo_owner, module.id, variant, outcome)
        brag = None
        if outcome == "win" and difficulty == "hard" and room.solo_owner is not None:
            size = room.solo_variant.get("size")
            brag = await self.brag_store.reward_bot_win(room.solo_owner, module.id, size)
        room.solo_result = {"outcome": outcome, "record": record, "brag": brag}
        started = room.game_started_at if room.game_started_at is not None else now
        recorder.record_event(
            "solo_finished",
            user_id=room.solo_owner,
            game_id=module.id,
            meta={
                "game_id": module.id,
                "difficulty": difficulty,
                "outcome": outcome,
                "duration": round((now - started) / 1000),
            },
        )
        await self._send_views(room, module)
        await self._broadcast_room(room)

    async def _challenge_finish(self, room: Room, module: Any, reason: str) -> None:
        """A run is over: plays + 1 and the best score, then soloResult with the outcome."""
        self._end_game_timers(room)
        now = self.clock()
        state = room.game_state
        game_id = room.selected_game or module.id
        variant = self._solo_variant_of(room, module, state)
        score = module.score(state)
        room.status, room.end_reason = "finished", reason
        saved = None
        if room.solo_owner is not None:
            saved = await self.solo_store.record_score(room.solo_owner, game_id, variant, score)
        room.solo_result = {
            "outcome": "run_over",
            "score": score,
            "detail": module.detail(state),
            "best": saved["bestScore"] if saved else None,
            "isNewBest": bool(saved) and score > saved["previousBest"],
            "record": {"plays": saved["plays"], "bestScore": saved["bestScore"]} if saved else None,
        }
        started = room.game_started_at if room.game_started_at is not None else now
        recorder.record_event(
            "solo_finished",
            user_id=room.solo_owner,
            game_id=game_id,
            meta={
                "game_id": game_id,
                "variant": variant,
                "score": score,
                "duration": round((now - started) / 1000),
            },
        )
        await self._send_views(room, module)
        await self._broadcast_room(room)

    # ----- the bot -----------------------------------------------------------------------

    def _drive_bot(self, room: Room) -> None:
        """After a state change: schedule the bot's move if the bot is due to act.

        A bot that keeps the turn (it just closed a box) goes on after the shorter continue
        delay; a real-time game's bot picks its own moment (no think delay).
        """
        room.bot_seq += 1
        self._cancel_bot(room)
        if room.status != "playing" or self.rooms.get(room.code) is not room:
            return
        module = self._module(room)
        bot = room.bot()
        if bot is None or not module.bot_due(room.game_state, bot.id):
            return
        rng = room.bot_rng or random.Random()
        if module.realtime:
            think = 0.0
        elif room.bot_continuing:
            think = rng.uniform(*self.bot_continue_ms)
        else:
            think = rng.uniform(*self.bot_think_ms)
        deadline = module.next_deadline(room.game_state)
        if deadline is not None:
            think = min(think, max(0.0, deadline - self.clock()) / 2)
        room.bot_task = asyncio.create_task(self._bot_turn(room, room.bot_seq, think / 1000))

    def _cancel_bot(self, room: Room) -> None:
        task = room.bot_task
        room.bot_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    def _bot_may_act(self, room: Room, seq: int) -> bool:
        return (
            room.bot_task is asyncio.current_task()
            and room.bot_seq == seq
            and self.rooms.get(room.code) is room
            and room.status == "playing"
        )

    async def _bot_turn(self, room: Room, seq: int, delay: float) -> None:
        await asyncio.sleep(delay)
        async with room.lock:
            if not self._bot_may_act(room, seq):
                return
            module = self._module(room)
            bot = room.bot()
            assert bot is not None
            view = {**module.seat_view(room.game_state, bot.id), "serverNow": self.clock()}
            rng = random.Random((room.bot_rng or random.Random()).getrandbits(64))
            difficulty = room.solo_variant.get("difficulty", DEFAULT_DIFFICULTY)
        choose = partial(CHOOSERS[module.id], view, rng, difficulty, self.bot_budget_ms)
        action: dict[str, Any] | None
        wait_ms = 0.0
        try:
            async with self.bot_slots:
                chosen = await asyncio.get_running_loop().run_in_executor(None, choose)
            action, wait_ms = chosen if isinstance(chosen, tuple) else (chosen, 0.0)
        except Exception:
            logger.exception("Bot move failed in room %s", room.code)
            action = None
        if wait_ms > 0:  # a real-time move at the bot's chosen moment (still guarded by seq)
            await asyncio.sleep(wait_ms / 1000)
        async with room.lock:
            if not self._bot_may_act(room, seq):
                return
            room.bot_task = None
            if action is None:
                action = module.fallback_action(room.game_state, bot.id, rng)
            room.bot_continuing = True
            try:
                await self._game_action(room, bot.id, action, lambda: True)
            except Exception:
                logger.exception("Bot move rejected in room %s", room.code)
            finally:
                room.bot_continuing = False

    # ----- idle close --------------------------------------------------------------------

    def _schedule_solo_idle(self, room: Room) -> None:
        self._cancel_solo_idle(room)
        room.idle_task = asyncio.create_task(self._solo_idle(room))

    def _cancel_solo_idle(self, room: Room) -> None:
        task = room.idle_task
        room.idle_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    async def _solo_idle(self, room: Room) -> None:
        """Close the solo room once nobody has been connected for SOLO_IDLE_TTL_MS."""
        await asyncio.sleep(self.solo_idle_ms / 1000)
        async with room.lock:
            if room.idle_task is not asyncio.current_task():
                return
            room.idle_task = None
            if self.rooms.get(room.code) is not room or any(
                p.online for p in room.seated() if not p.bot
            ):
                return
            await self._delete_room(room)
