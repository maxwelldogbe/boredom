"""Live social state over the WebSocket: which connections belong to which account, the
statuses friends see, and room invites. All in memory, owned by the RoomManager (one process).

Every method runs on the event loop. Code in other threads (HTTP views, database work) reaches
the hub through `call_soon`, which does nothing while no account has connected.

Status rules: offline (no connection, or presence mode "offline"); busy (mode "busy"); in_game
(seated in a "playing" room and still in the game); in_lobby (seated in any other room state);
otherwise online. When an account's last connection closes it stays as it was for
PRESENCE_OFFLINE_DELAY_MS, so a reconnect causes no offline flicker.

Pushes carry tags only to friends, and never carry room codes or room contents.
"""

import asyncio
import logging
import secrets
from collections import OrderedDict
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from channels.db import database_sync_to_async

from accounts.ratelimit import KeyedRateLimiter
from games import registry
from games.constants import (
    INVITE_COOLDOWN_MS,
    INVITE_TTL_MS,
    INVITES_PER_MINUTE,
    MAX_PENDING_INVITES_PER_USER,
    MAX_PLAYERS,
    PRESENCE_OFFLINE_DELAY_MS,
)
from rooms.models_types import Player, Room, RoomError
from social.errors import SocialError

if TYPE_CHECKING:
    from rooms.manager import RoomManager

logger = logging.getLogger("social.hub")

UNAVAILABLE = "That friend can't be invited right now."
EXPIRED_MEMORY = 1000  # recently expired invite ids kept, so accepting one says "expired"


@dataclass
class Account:
    """A signed-in account with at least one connection (or within the offline delay)."""

    user_id: int
    tag: str
    nickname: str
    avatar: dict[str, str]
    mode: str
    friends: set[int]
    channels: set[str] = field(default_factory=set)
    linger: asyncio.Task[None] | None = None


@dataclass
class Invite:
    id: str
    sender_id: int
    sender_player_id: str
    target_id: int
    room_code: str
    created_at: float
    expires_at: float
    payload: dict[str, Any]  # invite:received data, minus serverNow
    task: asyncio.Task[None] | None = None


class SocialHub:
    def __init__(self, manager: "RoomManager") -> None:
        self.manager = manager
        self.accounts: dict[int, Account] = {}
        self.owners: dict[str, int] = {}  # channel -> account
        self.tags: dict[int, str] = {}  # tags of signed-in accounts and their friends
        self.statuses: dict[int, str] = {}  # last status friends were told
        self.room_members: dict[str, set[int]] = {}  # room code -> registered seats last seen
        self.invites: dict[str, Invite] = {}
        self.expired: OrderedDict[str, int] = OrderedDict()  # invite id -> recipient
        self.cooldowns: dict[tuple[int, int], float] = {}
        self.invite_limiter = KeyedRateLimiter(INVITES_PER_MINUTE)
        self.offline_delay_ms: float = PRESENCE_OFFLINE_DELAY_MS
        self.invite_ttl_ms: float = INVITE_TTL_MS
        self.invite_cooldown_ms: float = INVITE_COOLDOWN_MS
        self.loop: asyncio.AbstractEventLoop | None = None
        self._tasks: set[asyncio.Task[Any]] = set()

    # ----- plumbing ----------------------------------------------------------------------------

    def call_soon(self, method: str, *args: Any) -> None:
        """Run `await self.<method>(*args)` on the hub's loop, from any thread."""
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._spawn(getattr(self, method)(*args))
        else:
            loop.call_soon_threadsafe(lambda: self._spawn(getattr(self, method)(*args)))

    def _spawn(self, coro: Awaitable[Any]) -> asyncio.Task[Any]:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._done)
        return task

    def _done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Social task failed", exc_info=task.exception())

    def tasks(self) -> list[asyncio.Task[Any]]:
        """Every task the hub still runs (for shutdown and tests)."""
        out = list(self._tasks)
        out += [a.linger for a in self.accounts.values() if a.linger]
        out += [i.task for i in self.invites.values() if i.task]
        return out

    async def _send(self, channels, type_: str, data: dict[str, Any]) -> None:
        message = {"type": "push", "message": {"type": type_, "data": data}}
        for channel in list(channels):
            await self.manager.send(channel, message)

    async def _to_account(self, user_id: int, type_: str, data: dict[str, Any]) -> None:
        account = self.accounts.get(user_id)
        if account is not None:
            await self._send(account.channels, type_, data)

    def user_of(self, channel: str) -> int | None:
        return self.owners.get(channel)

    # ----- status ------------------------------------------------------------------------------

    def _seat(self, user_id: int) -> tuple[Room, Player] | None:
        for room in self.manager.rooms.values():
            for player in room.players:
                if player.user_id == user_id and not player.left:
                    return room, player
        return None

    def status(self, user_id: int) -> str:
        account = self.accounts.get(user_id)
        if account is None or account.mode == "offline":
            return "offline"
        if account.mode == "busy":
            return "busy"
        seat = self._seat(user_id)
        if seat is None:
            return "online"
        room, player = seat
        return "in_game" if room.status == "playing" and player.in_game else "in_lobby"

    def _watchers(self, user_id: int) -> list[Account]:
        return [a for a in self.accounts.values() if user_id in a.friends]

    async def refresh(self, user_id: int) -> None:
        """Recompute one account's status and tell its signed-in friends if it changed."""
        status = self.status(user_id)
        if status == self.statuses.get(user_id, "offline"):
            return
        if status == "offline" and user_id not in self.accounts:
            self.statuses.pop(user_id, None)
        else:
            self.statuses[user_id] = status
        tag = self.tags.get(user_id)
        if tag is None:
            return
        for watcher in self._watchers(user_id):
            await self._send(watcher.channels, "friends:presence", {"tag": tag, "status": status})

    async def room_changed(self, room: Room) -> None:
        """After every room change (and its deletion): statuses and invites tied to the room."""
        alive = self.manager.rooms.get(room.code) is room
        members = {p.user_id for p in room.players if p.user_id is not None and not p.left}
        members = members if alive else set()
        affected = members | self.room_members.pop(room.code, set())
        if members:
            self.room_members[room.code] = members
        for user_id in affected:
            await self.refresh(user_id)
        for invite in [i for i in self.invites.values() if i.room_code == room.code]:
            if self._invite_problem(invite) is not None:
                await self._expire(invite)

    # ----- connections -------------------------------------------------------------------------

    async def hello(self, channel: str, info: dict[str, Any]) -> dict[str, Any]:
        """Bind `channel` to the account in `info` (from load_account); send the snapshot."""
        self.loop = asyncio.get_running_loop()
        user_id = info["userId"]
        if self.owners.get(channel) not in (None, user_id):
            await self.unbind(channel)
        account = self.accounts.get(user_id)
        if account is None:
            account = self.accounts[user_id] = Account(
                user_id, info["tag"], info["nickname"], info["avatar"], info["mode"], set()
            )
        account.nickname, account.avatar, account.mode = (
            info["nickname"],
            info["avatar"],
            info["mode"],
        )
        account.friends = set(info["friends"])
        if account.linger is not None:
            account.linger.cancel()
            account.linger = None
        account.channels.add(channel)
        self.owners[channel] = user_id
        self.tags[user_id] = account.tag
        self.tags.update(info["friends"])
        await self.refresh(user_id)
        snapshot = [
            {"tag": tag, "status": self.status(fid)} for fid, tag in info["friends"].items()
        ]
        await self._send([channel], "friends:snapshot", {"friends": snapshot})
        for invite in self.invites.values():
            if invite.target_id == user_id:
                await self._send([channel], "invite:received", self._received(invite))
        return {"presence": account.mode}

    async def unbind(self, channel: str) -> None:
        """The connection closed or signed out: drop it, then go offline after the delay."""
        user_id = self.owners.pop(channel, None)
        account = self.accounts.get(user_id) if user_id is not None else None
        if account is None:
            return
        account.channels.discard(channel)
        if not account.channels and account.linger is None:
            account.linger = asyncio.create_task(self._linger(account))

    async def _linger(self, account: Account) -> None:
        await asyncio.sleep(self.offline_delay_ms / 1000)
        if account.channels or self.accounts.get(account.user_id) is not account:
            return
        account.linger = None
        del self.accounts[account.user_id]
        await self.refresh(account.user_id)

    # ----- events from HTTP and database code (via call_soon) ---------------------------------

    async def mode_changed(self, user_id: int, mode: str) -> None:
        account = self.accounts.get(user_id)
        if account is not None:
            account.mode = mode
            await self.refresh(user_id)

    async def request_sent(self, to_id: int, request: dict[str, Any]) -> None:
        await self._to_account(to_id, "friends:request", {"request": request})

    async def friends_made(self, a: dict[str, Any], b: dict[str, Any]) -> None:
        """a and b are {userId, tag, nickname}; each side learns of the other."""
        for me, other in ((a, b), (b, a)):
            self.tags[other["userId"]] = other["tag"]
            account = self.accounts.get(me["userId"])
            if account is None:
                continue
            account.friends.add(other["userId"])
            accepted = {"tag": other["tag"], "nickname": other["nickname"]}
            await self._send(account.channels, "friends:accepted", accepted)
            presence = {"tag": other["tag"], "status": self.status(other["userId"])}
            await self._send(account.channels, "friends:presence", presence)

    async def friends_removed(self, a: dict[str, Any], b: dict[str, Any]) -> None:
        for me, other in ((a, b), (b, a)):
            account = self.accounts.get(me["userId"])
            if account is not None and other["userId"] in account.friends:
                account.friends.discard(other["userId"])
                await self._send(account.channels, "friends:removed", {"tag": other["tag"]})

    async def blocked(self, a_id: int, b_id: int) -> None:
        pair = {a_id, b_id}
        for invite in list(self.invites.values()):
            if {invite.sender_id, invite.target_id} == pair:
                await self._expire(invite)

    async def account_gone(self, user_id: int) -> None:
        """Disabled or deleted: signed out everywhere, off every friend list, invites gone."""
        account = self.accounts.pop(user_id, None)
        if account is not None:
            if account.linger is not None:
                account.linger.cancel()
            for channel in account.channels:
                self.owners.pop(channel, None)
        tag = self.tags.get(user_id)
        for watcher in self._watchers(user_id):
            watcher.friends.discard(user_id)
            if tag is not None:
                await self._send(watcher.channels, "friends:removed", {"tag": tag})
        self.statuses.pop(user_id, None)
        for invite in list(self.invites.values()):
            if user_id in (invite.sender_id, invite.target_id):
                await self._expire(invite)

    # ----- invites -----------------------------------------------------------------------------

    @staticmethod
    def room_full(room: Room) -> bool:
        cap = MAX_PLAYERS
        module = registry.get_game(room.selected_game) if room.selected_game else None
        if module is not None:
            cap = min(cap, module.max_players)
        return len(room.seated()) >= cap

    def _invite_problem(self, invite: Invite) -> str | None:
        """Why the invite can no longer be used: INVITE_EXPIRED or ROOM_FULL; None if fine."""
        room = self.manager.rooms.get(invite.room_code)
        sender = room.player(invite.sender_player_id) if room else None
        if room is None or room.status != "lobby" or sender is None or sender.left:
            return "INVITE_EXPIRED"
        if self.manager.clock() >= invite.expires_at:
            return "INVITE_EXPIRED"
        return "ROOM_FULL" if self.room_full(room) else None

    def _received(self, invite: Invite) -> dict[str, Any]:
        return {**invite.payload, "serverNow": self.manager.clock()}

    def _drop(self, invite: Invite) -> None:
        self.invites.pop(invite.id, None)
        if invite.task is not None and invite.task is not asyncio.current_task():
            invite.task.cancel()

    async def _expire(self, invite: Invite) -> None:
        if self.invites.get(invite.id) is not invite:
            return
        self._drop(invite)
        self.expired[invite.id] = invite.target_id
        while len(self.expired) > EXPIRED_MEMORY:
            self.expired.popitem(last=False)
        await self._to_account(invite.target_id, "invite:expired", {"inviteId": invite.id})

    async def _ttl(self, invite: Invite) -> None:
        await asyncio.sleep(max(0.0, invite.expires_at - self.manager.clock()) / 1000)
        await self._expire(invite)

    def _sender_seat(self, code: str | None, player_id: str | None) -> tuple[Room, Player]:
        room = self.manager.rooms.get(code or "")
        player = room.player(player_id or "") if room else None
        if room is None or player is None or player.left:
            raise RoomError("NOT_IN_ROOM", "You are not in a room.")
        if player.user_id is None:
            raise RoomError("INVALID_ACTION", "Sign in to invite friends.")
        return room, player

    def _check_lobby(self, room: Room) -> None:
        if room.status != "lobby":
            raise RoomError("INVALID_ACTION", "You can only invite friends from the lobby.")
        if self.room_full(room):
            raise RoomError("ROOM_FULL", "The room is full.")

    async def send_invite(self, code: str | None, player_id: str | None, tag: Any) -> None:
        room, player = self._sender_seat(code, player_id)
        self._check_lobby(room)
        sender_id = player.user_id
        assert sender_id is not None
        found = await invite_lookup(sender_id, tag)
        room, player = self._sender_seat(code, player_id)  # the room may have moved on
        self._check_lobby(room)
        if found is None:
            raise RoomError("NOT_FRIENDS", "You can only invite friends.")
        target_id, available, sender = found["targetId"], found["available"], found["sender"]
        if sender is None:
            raise RoomError("INVALID_ACTION", "Sign in to invite friends.")
        now = self.manager.clock()
        last = self.cooldowns.get((sender_id, target_id))
        if last is not None and now - last < self.invite_cooldown_ms:
            raise RoomError("RATE_LIMITED", "You just invited them. Give them a moment.")
        if not self.invite_limiter.allow(f"user:{sender_id}"):
            raise RoomError("RATE_LIMITED", "Too many invites. Wait a minute.")
        if not available or self.status(target_id) != "online":
            raise RoomError("TARGET_UNAVAILABLE", UNAVAILABLE)
        self.cooldowns = {
            k: t for k, t in self.cooldowns.items() if now - t < self.invite_cooldown_ms
        }
        self.cooldowns[(sender_id, target_id)] = now
        pending = sorted(
            (i for i in self.invites.values() if i.target_id == target_id),
            key=lambda i: i.created_at,
        )
        for old in pending:
            if old.sender_id == sender_id:
                await self._expire(old)  # a fresh invite replaces the older one
        pending = [i for i in pending if i.id in self.invites]
        for old in pending[: max(0, len(pending) - MAX_PENDING_INVITES_PER_USER + 1)]:
            await self._expire(old)
        invite = Invite(
            id="i_" + secrets.token_hex(8),
            sender_id=sender_id,
            sender_player_id=player.id,
            target_id=target_id,
            room_code=room.code,
            created_at=now,
            expires_at=now + self.invite_ttl_ms,
            payload={},
        )
        invite.payload = {
            "inviteId": invite.id,
            "fromTag": sender["tag"],
            "fromNickname": sender["nickname"],
            "fromAvatar": sender["avatar"],
            "gameId": room.selected_game,
            "expiresAt": invite.expires_at,
        }
        self.invites[invite.id] = invite
        invite.task = asyncio.create_task(self._ttl(invite))
        await self._to_account(target_id, "invite:received", self._received(invite))

    def _own_invite(self, channel: str, invite_id: Any) -> Invite | None:
        user_id = self.owners.get(channel)
        invite = self.invites.get(invite_id) if isinstance(invite_id, str) else None
        if invite is None or user_id is None or invite.target_id != user_id:
            return None
        return invite

    async def _clear_elsewhere(self, invite: Invite, channel: str) -> None:
        """The recipient answered on one device: the invite goes away on the others."""
        account = self.accounts.get(invite.target_id)
        if account is not None:
            others = account.channels - {channel}
            await self._send(others, "invite:cleared", {"inviteId": invite.id})

    async def accept_invite(self, channel: str, invite_id: Any) -> dict[str, Any]:
        invite = self._own_invite(channel, invite_id)
        if invite is None:
            mine = self.owners.get(channel)
            if (
                mine is not None
                and isinstance(invite_id, str)
                and self.expired.get(invite_id) == mine
            ):
                raise RoomError("INVITE_EXPIRED", "That invite has expired.")
            raise RoomError("INVITE_INVALID", "That invite is no longer available.")
        blocked = await is_blocked(invite.sender_id, invite.target_id)
        if self.invites.get(invite.id) is not invite:
            raise RoomError("INVITE_INVALID", "That invite is no longer available.")
        if blocked:
            self._drop(invite)
            raise RoomError("INVITE_INVALID", "That invite is no longer available.")
        problem = self._invite_problem(invite)
        if problem == "INVITE_EXPIRED":
            await self._expire(invite)
            raise RoomError("INVITE_EXPIRED", "That invite has expired.")
        if problem == "ROOM_FULL":
            await self._expire(invite)
            raise RoomError("ROOM_FULL", "The room is full.")
        self._drop(invite)
        await self._clear_elsewhere(invite, channel)
        return {"code": invite.room_code}

    async def decline_invite(self, channel: str, invite_id: Any) -> None:
        invite = self._own_invite(channel, invite_id)
        if invite is not None:
            self._drop(invite)
            await self._clear_elsewhere(invite, channel)

    # ----- room context actions by playerId ----------------------------------------------------

    def seat_pair(
        self, code: str | None, player_id: str | None, target_id: Any
    ) -> tuple[Room, Player, Player]:
        """The sender's and the target's seats, both seated in the sender's room."""
        room = self.manager.rooms.get(code or "")
        me = room.player(player_id or "") if room else None
        if room is None or me is None or me.left:
            raise RoomError("NOT_IN_ROOM", "You are not in a room.")
        if me.user_id is None:
            raise RoomError("INVALID_ACTION", "Sign in to do that.")
        other = room.player(target_id) if isinstance(target_id, str) else None
        if other is None or other.left or other.id == me.id:
            raise RoomError("INVALID_ACTION", "That player is not in this room.")
        return room, me, other


# ----- database helpers (run in a worker thread) -------------------------------------------------


@database_sync_to_async
def load_account(user_id: int) -> dict[str, Any] | None:
    """What the hub needs to bind a connection, or None for a missing or disabled account."""
    from accounts.models import Profile
    from accounts.tags import ensure_tag
    from social.services import friend_ids

    profile = Profile.objects.filter(user_id=user_id, user__is_active=True).first()
    if profile is None:
        return None
    friends = Profile.objects.filter(user_id__in=friend_ids(user_id))
    return {
        "userId": user_id,
        "tag": ensure_tag(profile),
        "nickname": profile.nickname,
        "avatar": {"style": profile.avatar_style, "seed": profile.avatar_seed},
        "mode": profile.presence_mode,
        "friends": {p.user_id: ensure_tag(p) for p in friends},
    }


@database_sync_to_async
def invite_lookup(sender_id: int, raw_tag: Any) -> dict[str, Any] | None:
    """None unless the tag names a friend (a block counts as a friend that is unavailable)."""
    from social import services
    from social.models import Friendship

    try:
        target = services.profile_by_tag(raw_tag)
    except SocialError:
        return None
    target_id = target.user_id
    blocked = services.blocked_either(sender_id, target_id)
    low, high = sorted((sender_id, target_id))
    friends = Friendship.objects.filter(user_low_id=low, user_high_id=high).exists()
    if not friends and not blocked:
        return None
    from accounts.models import Profile

    sender = Profile.objects.filter(user_id=sender_id, user__is_active=True).first()
    return {
        "targetId": target_id,
        "available": friends and not blocked and target.user.is_active,
        "sender": None
        if sender is None
        else {
            "tag": sender.tag,
            "nickname": sender.nickname,
            "avatar": {"style": sender.avatar_style, "seed": sender.avatar_seed},
        },
    }


@database_sync_to_async
def is_blocked(a: int, b: int) -> bool:
    from social.services import blocked_either

    return blocked_either(a, b)


@database_sync_to_async
def player_action(kind: str, sender_id: int, target: Player, room: Room, payload: dict) -> dict:
    """friends:requestByPlayer, player:block or player:report on a seat in the same room.

    The same service functions and limits as the HTTP API (SocialError on failure).
    """
    from django.contrib.auth.models import User

    from accounts.models import Profile
    from social import services

    sender = User.objects.select_related("profile").filter(pk=sender_id, is_active=True).first()
    if sender is None or not hasattr(sender, "profile"):
        raise SocialError("INVALID_ACTION", "Sign in to do that.")
    profile = None
    if target.user_id is not None:
        profile = Profile.objects.select_related("user").filter(user_id=target.user_id).first()
    if kind == "player:report":
        services.report(
            sender,
            payload.get("reason"),
            payload.get("note"),
            target=profile,
            guest_key=target.guest_key,
            nickname=target.nickname,
            room_code=room.code,
            game_id=room.game_id or room.selected_game or "",
        )
        return {}
    if profile is None:
        raise SocialError("INVALID_ACTION", "That player doesn't have an account.")
    if kind == "friends:requestByPlayer":
        return services.send_request(sender, profile)
    services.block(sender, profile)
    return {}
