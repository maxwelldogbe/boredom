"""Upkeep half of the room manager: host transfer, idle cleanup, room deletion.

Mixed into RoomManager.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from rooms import hooks
from rooms.models_types import Room

logger = logging.getLogger("rooms.upkeep")


class UpkeepMixin:
    """Background housekeeping. Requires the RoomManager attributes."""

    rooms: dict[str, Room]
    clock: Callable[[], float]
    send: Callable[[str, dict[str, Any]], Awaitable[None]]
    host_transfer_ms: float
    idle_ttl_ms: float
    cleanup_interval_ms: float
    _cleanup_task: asyncio.Task[None] | None

    # ----- host transfer ---------------------------------------------------------------

    def _transfer_host(self, room: Room, allow_offline: bool) -> bool:
        """Pass host to the longest-seated online player (or any seated one if allowed)."""
        others = [p for p in room.seated() if p.id != room.host_id]
        candidates = [p for p in others if p.online] or (others if allow_offline else [])
        if not candidates:
            return False
        room.host_id = min(candidates, key=lambda p: p.joined_at).id
        return True

    async def _transfer_host_announced(self, room: Room, allow_offline: bool) -> bool:
        """Transfer host and, if it moved, tell everyone with a host_changed event."""
        previous = room.host_id
        if not self._transfer_host(room, allow_offline):
            return False
        host = room.host()
        assert host is not None
        await self._room_event(room, "host_changed", host, {"previousHostId": previous})
        return True

    def _schedule_host_check(self, room: Room) -> None:
        if room.host_task is not None:
            room.host_task.cancel()
        room.host_task = asyncio.create_task(self._host_check(room))

    async def _host_check(self, room: Room) -> None:
        """After HOST_TRANSFER_MS offline, hand host to someone online."""
        await asyncio.sleep(self.host_transfer_ms / 1000)
        async with room.lock:
            room.host_task = None
            host = room.host()
            if self.rooms.get(room.code) is not room or host is None or host.online:
                return
            if await self._transfer_host_announced(room, allow_offline=False):
                await self._broadcast_room(room)

    # ----- cleanup -----------------------------------------------------------------------

    def ensure_cleanup_task(self) -> None:
        """Start the idle-cleanup loop on the running event loop if it is not running."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.cleanup_interval_ms / 1000)
            try:
                await self.cleanup()
            except Exception:
                logger.exception("Room cleanup failed")

    async def cleanup(self) -> list[str]:
        """Delete rooms that are empty or idle beyond ROOM_IDLE_TTL_MS. Returns their codes."""
        removed = []
        for room in list(self.rooms.values()):
            async with room.lock:
                idle = self.clock() - room.last_activity > self.idle_ttl_ms
                if self.rooms.get(room.code) is room and (idle or not room.seated()):
                    await self._delete_room(room)
                    removed.append(room.code)
        return removed

    async def _delete_room(self, room: Room) -> None:
        """Remove a room, stop its timers and tell any still-connected sockets.

        A room removed mid-game (everyone left, or idle cleanup) records the game as abandoned.
        """
        if room.status == "playing" and room.game_id:
            try:
                hooks.on_game_abandoned(hooks.game_record(room, room.game_id, self.clock(), None))
            except Exception:
                logger.exception("Game-abandoned hook failed: room=%s", room.code)
        self._end_game_timers(room)
        for player_id in list(room.notice_tasks):
            self._cancel_notice(room, player_id)
        if room.host_task is not None:
            room.host_task.cancel()
            room.host_task = None
        self.rooms.pop(room.code, None)
        for player in room.players:
            if player.channel:
                await self._detach(player.channel, room.code, "This room was closed.")
        logger.info("Room %s deleted", room.code)

