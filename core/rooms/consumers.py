"""The /ws/ consumer: parse, rate-limit, delegate to the RoomManager, reply with an ack."""

import json
import logging
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer

from accounts.rooms import account_profile
from accounts.tokens import user_id_from_token
from rooms import manager as manager_module
from rooms.manager import RoomManager
from rooms.models_types import Profile, RoomError
from rooms.validation import (
    REQUEST_TYPES,
    BadMessage,
    RateLimiter,
    Request,
    normalize_code,
    optional_token,
    parse_request,
    validate_profile,
)
from social import hub as social_hub

SOCIAL_BY_PLAYER = ("friends:requestByPlayer", "player:block", "player:report")

logger = logging.getLogger("rooms.consumers")


def get_manager() -> RoomManager:
    """The process-wide manager (looked up at call time so tests can swap it)."""
    return manager_module.manager


class RoomConsumer(AsyncWebsocketConsumer):
    """One connection = at most one seat in one room."""

    room_code: str | None = None
    player_id: str | None = None

    async def connect(self) -> None:
        self.limiter = RateLimiter()
        get_manager().ensure_cleanup_task()
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        if self.room_code:
            await get_manager().disconnect(self.room_code, self.player_id, self.channel_name)
        await get_manager().social.unbind(self.channel_name)

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        try:
            request = parse_request(text_data)
        except BadMessage as exc:
            error = {"code": "BAD_MESSAGE", "message": exc.message}
            if exc.request_id is None:
                await self._send({"type": "error", "data": error})
            else:
                await self._send({"type": "ack", "id": exc.request_id, "ok": False, "error": error})
            return
        try:
            data = await self._dispatch(request)
        except RoomError as exc:
            if exc.code == "NOT_IN_ROOM":
                self.room_code = self.player_id = None
            error = {"code": exc.code, "message": exc.message}
            if exc.data is not None:
                error["data"] = exc.data
            await self._send({"type": "ack", "id": request.id, "ok": False, "error": error})
            return
        except Exception:
            logger.exception("Unhandled error for %s", request.type)
            error = {"code": "INVALID_ACTION", "message": "Something went wrong."}
            await self._send({"type": "ack", "id": request.id, "ok": False, "error": error})
            return
        await self._send({"type": "ack", "id": request.id, "ok": True, "data": data})

    async def _dispatch(self, request: Request) -> dict[str, Any]:
        """Route one request to the manager and return the ack data."""
        if request.type not in REQUEST_TYPES:
            raise RoomError("UNKNOWN_EVENT", f"Unknown event {request.type[:40]!r}.")
        manager, payload = get_manager(), request.payload
        if request.type == "room:peek":
            try:
                return manager.peek(normalize_code(payload.get("code")))
            except RoomError:
                return manager.peek(None)
        if request.type == "auth:hello":
            return await self._hello(payload)
        if request.type == "invite:accept":
            return await manager.social.accept_invite(self.channel_name, payload.get("inviteId"))
        if request.type == "invite:decline":
            await manager.social.decline_invite(self.channel_name, payload.get("inviteId"))
            return {}
        if request.type == "guest:quota":
            return await manager.guest_quota(payload.get("profile"))
        if request.type in ("room:create", "room:join"):
            if self.room_code and self.room_code in manager.rooms:
                raise RoomError("INVALID_ACTION", "Leave your current room first.")
            profile, auth_status = await self._profile(payload)
            if request.type == "room:create":
                data = await manager.create_room(self.channel_name, profile)
            else:
                code = normalize_code(payload.get("code"))
                token = optional_token(payload.get("roomToken"))
                data = await manager.join_room(self.channel_name, code, profile, token)
            self.room_code, self.player_id = data["room"]["code"], data["playerId"]
            return {**data, "authStatus": auth_status} if auth_status else data
        if not self.room_code:
            raise RoomError("NOT_IN_ROOM", "You are not in a room.")
        code, pid = self.room_code, self.player_id
        if request.type == "room:leave":
            await manager.leave_room(code, pid)
            self.room_code = self.player_id = None
        elif request.type == "room:selectGame":
            await manager.select_game(code, pid, payload.get("gameId"), payload.get("settings"))
        elif request.type == "game:start":
            await manager.start_game(code, pid)
        elif request.type == "game:action":
            await manager.game_action(code, pid, payload, self.limiter.allow)
        elif request.type == "game:playAgain":
            await manager.play_again(code, pid)
        elif request.type == "game:quit":
            await manager.quit_game(code, pid)
        elif request.type == "game:end":
            await manager.end_game(code, pid)
        elif request.type == "room:ready":
            await manager.set_ready(code, pid, payload.get("ready"))
        elif request.type == "room:react":
            await manager.react(code, pid, payload.get("emoji"))
        elif request.type == "invite:send":
            await manager.social.send_invite(code, pid, payload.get("tag"))
        elif request.type in SOCIAL_BY_PLAYER:
            room, me, target = manager.social.seat_pair(code, pid, payload.get("playerId"))
            assert me.user_id is not None
            try:
                return await social_hub.player_action(
                    request.type, me.user_id, target, room, payload
                )
            except social_hub.SocialError as exc:
                raise RoomError(exc.code, exc.message) from None
        return {}

    async def _hello(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Bind this connection to the account in authToken (presence and invites)."""
        hub = get_manager().social
        user_id = user_id_from_token(payload.get("authToken"))
        info = await social_hub.load_account(user_id) if user_id is not None else None
        if info is None:
            await hub.unbind(self.channel_name)
            raise RoomError("UNAUTHORIZED", "Please sign in again.")
        return await hub.hello(self.channel_name, info)

    @staticmethod
    async def _profile(payload: dict[str, Any]) -> tuple[Profile, str | None]:
        """The seat's profile and the authStatus to report (None when there is nothing to say).

        A valid authToken loads the account's saved profile and the client's profile fields
        are ignored. An invalid or expired one falls back to the guest profile.
        """
        token = payload.get("authToken")
        if token is not None:
            account = await account_profile(token)
            if account is not None:
                return account, None
            return validate_profile(payload.get("profile")), "invalid"
        return validate_profile(payload.get("profile")), None

    async def push(self, event: dict[str, Any]) -> None:
        """Channel-layer handler: forward a server push to this socket."""
        await self._send(event["message"])

    async def room_detach(self, event: dict[str, Any]) -> None:
        """Channel-layer handler: this socket lost its seat (room closed or seat reclaimed)."""
        if event.get("code") == self.room_code:
            self.room_code = self.player_id = None
            error = {"code": "NOT_IN_ROOM", "message": event.get("message", "")}
            await self._send({"type": "error", "data": error})

    async def _send(self, message: dict[str, Any]) -> None:
        await self.send(text_data=json.dumps(message, ensure_ascii=False))
