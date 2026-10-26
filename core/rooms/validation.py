"""Validation of incoming messages, profiles and room codes, plus the per-connection rate limit."""

import json
import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from games.constants import (
    ACTION_RATE_LIMIT_PER_SEC,
    NICKNAME_ALLOWED_PATTERN,
    NICKNAME_MAX,
    NICKNAME_MIN,
    PLAYER_COLORS,
    ROOM_CODE_ALPHABET,
    ROOM_CODE_LENGTH,
)
from rooms.avatars import validate_avatar
from rooms.models_types import Profile, RoomError

REQUEST_TYPES = frozenset(
    {
        "room:create",
        "room:join",
        "room:peek",
        "room:leave",
        "room:selectGame",
        "game:start",
        "game:action",
        "game:playAgain",
        "game:quit",
        "game:end",
    }
)
MAX_MESSAGE_CHARS = 8192
PROFILE_ID_MAX = 64
ROOM_TOKEN_MAX = 64

_NICKNAME_RE = re.compile(NICKNAME_ALLOWED_PATTERN)
_COLORS = {c.upper(): c for c in PLAYER_COLORS}


@dataclass(frozen=True)
class Request:
    """A well-formed client request."""

    id: int
    type: str
    payload: dict[str, Any]


class BadMessage(Exception):
    """The frame is unusable. `request_id` is set when an ack can still be addressed."""

    def __init__(self, message: str, request_id: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.request_id = request_id


def parse_request(text: str | None) -> Request:
    """Parse a text frame into a Request, or raise BadMessage."""
    if text is None:
        raise BadMessage("Only text frames are accepted.")
    if len(text) > MAX_MESSAGE_CHARS:
        raise BadMessage("Message too large.")
    try:
        data = json.loads(text)
    except ValueError:
        raise BadMessage("Message is not valid JSON.") from None
    if not isinstance(data, dict):
        raise BadMessage("Message must be a JSON object.")
    request_id = data.get("id")
    if not isinstance(request_id, int) or isinstance(request_id, bool):
        raise BadMessage("Message needs an integer id.")
    msg_type = data.get("type")
    payload = data.get("payload")
    if not isinstance(msg_type, str) or not isinstance(payload, dict):
        raise BadMessage("Message needs a string type and an object payload.", request_id)
    return Request(request_id, msg_type, payload)


def validate_profile(raw: Any) -> Profile:
    """Validate and sanitize a client profile. Raises RoomError(INVALID_ACTION)."""
    if not isinstance(raw, dict):
        raise RoomError("INVALID_ACTION", "Profile is missing.")
    profile_id = raw.get("id")
    if not isinstance(profile_id, str) or not 0 < len(profile_id.strip()) <= PROFILE_ID_MAX:
        raise RoomError("INVALID_ACTION", "Profile id is invalid.")
    nickname = validate_nickname(raw.get("nickname"))
    color = validate_color(raw.get("color"))
    raw_avatar = raw.get("avatar")
    avatar = validate_avatar(raw_avatar) if raw_avatar is not None else None
    return Profile(id=profile_id.strip(), nickname=nickname, color=color, avatar=avatar)


def validate_nickname(raw: Any) -> str:
    """The trimmed nickname, or RoomError(INVALID_ACTION). Shared with saved account profiles."""
    if not isinstance(raw, str):
        raise RoomError("INVALID_ACTION", "Nickname is required.")
    nickname = raw.strip()
    if not NICKNAME_MIN <= len(nickname) <= NICKNAME_MAX:
        raise RoomError(
            "INVALID_ACTION", f"Nickname must be {NICKNAME_MIN} to {NICKNAME_MAX} characters."
        )
    if not _NICKNAME_RE.fullmatch(nickname):
        raise RoomError("INVALID_ACTION", "Nickname has characters that are not allowed.")
    return nickname


def validate_color(raw: Any) -> str:
    """The palette color in canonical case, or RoomError(INVALID_ACTION)."""
    canonical = _COLORS.get(raw.upper()) if isinstance(raw, str) else None
    if canonical is None:
        raise RoomError("INVALID_ACTION", "Pick one of the palette colors.")
    return canonical


def normalize_code(raw: Any) -> str:
    """Uppercase a room code and check its format. Unknown-format codes cannot exist."""
    if not isinstance(raw, str):
        raise RoomError("ROOM_NOT_FOUND", "Room code is missing.")
    code = raw.strip().upper()
    if len(code) != ROOM_CODE_LENGTH or any(ch not in ROOM_CODE_ALPHABET for ch in code):
        raise RoomError("ROOM_NOT_FOUND", f"We couldn't find room {code[:8]}.")
    return code


def optional_token(raw: Any) -> str | None:
    """Accept a roomToken string or nothing."""
    if raw is None:
        return None
    if not isinstance(raw, str) or len(raw) > ROOM_TOKEN_MAX:
        raise RoomError("INVALID_ACTION", "roomToken is invalid.")
    return raw


def unique_nickname(wanted: str, taken: list[str]) -> str:
    """Return `wanted`, or `wanted` with the lowest free suffix from 2 (Sam, Sam2, Sam3).

    Comparison ignores case. The base is shortened if needed to stay within NICKNAME_MAX.
    """
    used = {name.lower() for name in taken}
    if wanted.lower() not in used:
        return wanted
    n = 2
    while True:
        suffix = str(n)
        candidate = wanted[: NICKNAME_MAX - len(suffix)].rstrip() + suffix
        if candidate.lower() not in used:
            return candidate
        n += 1


class RateLimiter:
    """Sliding window (one second by default) allowing `limit` accepted calls."""

    def __init__(
        self,
        limit: int = ACTION_RATE_LIMIT_PER_SEC,
        clock: Callable[[], float] = time.monotonic,
        window: float = 1.0,
    ) -> None:
        self.limit = limit
        self.clock = clock
        self.window = window
        self._hits: deque[float] = deque()

    def idle(self) -> bool:
        """True when no accepted call is still inside the window."""
        return not self._hits or self.clock() - self._hits[-1] >= self.window

    def allow(self) -> bool:
        """Record and allow a call, or return False if the window is full."""
        now = self.clock()
        while self._hits and now - self._hits[0] >= self.window:
            self._hits.popleft()
        if len(self._hits) >= self.limit:
            return False
        self._hits.append(now)
        return True
