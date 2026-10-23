"""The single in-memory RoomManager: rooms, seats, hosts, presence, cleanup.

Every state change happens under the room's asyncio.Lock and is followed by a broadcast.
The server must run as ONE process: this object is the only copy of every room.
"""

import asyncio
import logging
import random
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any

from channels.layers import get_channel_layer

from analytics.keys import guest_key
from games import registry
from games.base import GameError
from games.constants import (
    HOST_TRANSFER_MS,
    MAX_PLAYERS,
    ROOM_CLEANUP_INTERVAL_MS,
    ROOM_CODE_ALPHABET,
    ROOM_CODE_LENGTH,
    ROOM_CODE_MAX_ATTEMPTS,
    ROOM_IDLE_TTL_MS,
)
from rooms import hooks
from rooms.avatars import AvatarRng, SystemAvatarRng, assign_avatar
from rooms.game_flow import GameFlowMixin
from rooms.models_types import Player, Profile, Room, RoomError
from rooms.upkeep import UpkeepMixin
from rooms.validation import unique_nickname

logger = logging.getLogger("rooms.manager")

SendFn = Callable[[str, dict[str, Any]], Awaitable[None]]


async def channel_layer_send(channel: str, event: dict[str, Any]) -> None:
    """Deliver an event to one consumer through the (in-memory) channel layer."""
    await get_channel_layer().send(channel, event)


def wall_clock_ms() -> float:
    """Epoch milliseconds, the unit of every `now` passed to game modules."""
    return time.time() * 1000


class RoomManager(UpkeepMixin, GameFlowMixin):
    """Owns every room. Methods raise RoomError for protocol errors."""

    def __init__(
        self,
        send: SendFn = channel_layer_send,
        clock: Callable[[], float] = wall_clock_ms,
        rng_factory: Callable[[], random.Random] = lambda: random.Random(secrets.randbits(64)),
        avatar_rng: AvatarRng | None = None,
    ) -> None:
        self.rooms: dict[str, Room] = {}
        self.send = send
        self.clock = clock
        self.rng_factory = rng_factory
        self.avatar_rng: AvatarRng = avatar_rng or SystemAvatarRng()
        self.host_transfer_ms: float = HOST_TRANSFER_MS
        self.idle_ttl_ms: float = ROOM_IDLE_TTL_MS
        self.cleanup_interval_ms: float = ROOM_CLEANUP_INTERVAL_MS
        self._cleanup_task: asyncio.Task[None] | None = None

    # ----- helpers -------------------------------------------------------------------

    def _rng(self) -> random.Random:
        return self.rng_factory()

    def _new_code(self) -> str:
        for _ in range(ROOM_CODE_MAX_ATTEMPTS):
            code = "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))
            if code not in self.rooms:
                return code
        raise RuntimeError("Could not allocate a free room code.")

    def _room(self, code: str | None) -> Room:
        room = self.rooms.get(code or "")
        if room is None:
            raise RoomError("NOT_IN_ROOM", "You are not in a room.")
        return room

    @staticmethod
    def _member(room: Room, player_id: str | None) -> Player:
        player = room.player(player_id or "")
        if player is None or player.left:
            raise RoomError("NOT_IN_ROOM", "You are not in this room.")
        return player

    @staticmethod
    def _require_host(room: Room, player: Player) -> None:
        if room.host_id != player.id:
            raise RoomError("NOT_HOST", "Only the host can do that.")

    @staticmethod
    def _seat_for_token(room: Room, token: str | None) -> Player | None:
        """The seat a valid roomToken belongs to (tokens of departed players are cleared)."""
        if not token:
            return None
        for player in room.players:
            if player.token and not player.left and secrets.compare_digest(player.token, token):
                return player
        return None

    @staticmethod
    def _seat_for_account(room: Room, user_id: int | None) -> Player | None:
        """The seat an account already holds here: one account never gets two seats."""
        if user_id is None:
            return None
        return next((p for p in room.players if p.user_id == user_id and not p.left), None)

    def _seat_reply(self, room: Room, player: Player) -> dict[str, Any]:
        return {"playerId": player.id, "roomToken": player.token, "room": room.to_public()}

    async def _push(self, room: Room, message: dict[str, Any]) -> None:
        """Send the same push to every online player."""
        for player in room.players:
            if player.online and player.channel:
                await self.send(player.channel, {"type": "push", "message": message})

    async def _detach(self, channel: str, code: str, message: str) -> None:
        """Tell a socket it no longer holds a seat in room `code`."""
        await self.send(channel, {"type": "room.detach", "code": code, "message": message})

    async def _broadcast_room(self, room: Room) -> None:
        await self._push(room, {"type": "room:state", "data": room.to_public()})

    def _new_player(self, room: Room, profile: Profile, channel: str) -> Player:
        nickname = unique_nickname(profile.nickname, [p.nickname for p in room.players])
        return Player(
            id="p_" + secrets.token_hex(6),
            profile_id=profile.id,
            nickname=nickname,
            color=profile.color,
            avatar=assign_avatar(profile, self.avatar_rng, taken={p.avatar for p in room.players}),
            joined_at=self.clock(),
            token=secrets.token_urlsafe(16),
            channel=channel,
            user_id=profile.user_id,
            guest_key="" if profile.user_id is not None else guest_key(profile.id),
        )

    # ----- requests ------------------------------------------------------------------

    async def create_room(self, channel: str, profile: Profile) -> dict[str, Any]:
        """Create a room with the sender as host."""
        now = self.clock()
        room = Room(code=self._new_code(), host_id="", created_at=now, last_activity=now)
        self.rooms[room.code] = room
        async with room.lock:
            player = self._new_player(room, profile, channel)
            room.players.append(player)
            room.host_id = player.id
            await self._broadcast_room(room)
            hooks.on_room_event("room_created", room.code, player)
            return self._seat_reply(room, player)

    async def join_room(
        self, channel: str, code: str, profile: Profile, token: str | None
    ) -> dict[str, Any]:
        """Take a new seat, or reclaim one by token or by account (detaching any older socket)."""
        room = self.rooms.get(code)
        if room is None:
            raise RoomError("ROOM_NOT_FOUND", f"We couldn't find room {code}.")
        async with room.lock:
            room.last_activity = self.clock()
            seat = self._seat_for_token(room, token) or self._seat_for_account(
                room, profile.user_id
            )
            if seat is not None:
                if seat.channel and seat.channel != channel:
                    await self._detach(seat.channel, room.code, "You joined from another tab.")
                seat.channel, seat.online, seat.offline_since = channel, True, None
                await self._broadcast_room(room)
                await self._presence_changed(room, seat.id, True)
                return self._seat_reply(room, seat)
            if room.status == "playing":
                raise RoomError("GAME_IN_PROGRESS", "A game is in progress. Join when it ends.")
            if len(room.players) >= MAX_PLAYERS:
                raise RoomError("ROOM_FULL", f"This room is full ({MAX_PLAYERS} players).")
            player = self._new_player(room, profile, channel)
            room.players.append(player)
            await self._broadcast_room(room)
            hooks.on_room_event("room_joined", room.code, player)
            return self._seat_reply(room, player)

    def peek(self, code: str | None) -> dict[str, Any]:
        """Public summary of a room for invite landing pages. Never fails, never leaks."""
        room = self.rooms.get(code or "")
        if room is None:
            return {"exists": False, "hostNickname": None, "playerCount": 0, "status": None}
        host = room.host()
        return {
            "exists": True,
            "hostNickname": host.nickname if host else None,
            "playerCount": len(room.seated()),
            "status": room.status,
        }

    async def leave_room(self, code: str | None, player_id: str | None) -> None:
        """Leave voluntarily. Mid-game the seat stays (offline) until the game ends."""
        room = self._room(code)
        async with room.lock:
            player = self._member(room, player_id)
            room.last_activity = self.clock()
            player.channel, player.online, player.offline_since = None, False, self.clock()
            player.token = ""
            hooks.on_room_event("room_left", room.code, player)
            if room.status == "playing":
                player.left = True
            else:
                room.players.remove(player)
                room.scoreboard.pop(player.id, None)
                room.wins.pop(player.id, None)
            if not room.seated():
                await self._delete_room(room)
                return
            if room.host_id == player.id:
                self._transfer_host(room, allow_offline=True)
            await self._broadcast_room(room)
            await self._presence_changed(room, player.id, False)

    async def disconnect(self, code: str | None, player_id: str | None, channel: str) -> None:
        """Socket closed: mark the seat offline (if this socket still owns it)."""
        room = self.rooms.get(code or "")
        if room is None:
            return
        async with room.lock:
            player = room.player(player_id or "")
            if player is None or player.left or player.channel != channel:
                return
            player.channel, player.online, player.offline_since = None, False, self.clock()
            if room.host_id == player.id:
                self._schedule_host_check(room)
            await self._broadcast_room(room)
            await self._presence_changed(room, player.id, False)

    async def select_game(
        self, code: str | None, player_id: str | None, game_id: Any, settings: Any
    ) -> None:
        """Host picks the game and its settings (validated by the module)."""
        room = self._room(code)
        async with room.lock:
            self._require_host(room, self._member(room, player_id))
            self._require_lobby(room)
            module = registry.get_game(game_id) if isinstance(game_id, str) else None
            if module is None:
                raise RoomError("INVALID_ACTION", "Unknown game.")
            if not isinstance(settings, dict):
                raise RoomError("INVALID_ACTION", "Settings must be an object.")
            try:
                cleaned = module.validate_settings(settings)
            except GameError as exc:
                raise RoomError(exc.code, exc.message) from None
            room.selected_game, room.settings = module.id, cleaned
            room.last_activity = self.clock()
            await self._broadcast_room(room)

    async def start_game(self, code: str | None, player_id: str | None) -> None:
        """Host starts the selected game."""
        room = self._room(code)
        async with room.lock:
            self._require_host(room, self._member(room, player_id))
            self._require_lobby(room)
            await self._start_game(room)

    async def game_action(
        self,
        code: str | None,
        player_id: str | None,
        action: dict[str, Any],
        allow: Callable[[], bool],
    ) -> None:
        """A move in the running game. `allow` is the connection's rate limiter."""
        room = self._room(code)
        async with room.lock:
            self._member(room, player_id)
            await self._game_action(room, player_id or "", action, allow)

    async def play_again(self, code: str | None, player_id: str | None) -> None:
        """Host returns a finished room to the lobby; scoreboard and selection are kept."""
        room = self._room(code)
        async with room.lock:
            self._require_host(room, self._member(room, player_id))
            if room.status == "playing":
                raise RoomError("GAME_IN_PROGRESS", "A game is still in progress.")
            room.status, room.game_id, room.game_state = "lobby", None, None
            room.last_activity = self.clock()
            await self._broadcast_room(room)

    @staticmethod
    def _require_lobby(room: Room) -> None:
        if room.status == "playing":
            raise RoomError("GAME_IN_PROGRESS", "A game is in progress.")
        if room.status != "lobby":
            raise RoomError("INVALID_ACTION", "Return to the lobby first.")


manager = RoomManager()
