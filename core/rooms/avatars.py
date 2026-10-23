"""DiceBear avatar assignment and validation.

An avatar is only {style, seed}. Seeds are random and never derived from the nickname,
profile id or anything else identifying.
"""

import random
import re
import secrets
from collections.abc import Collection, Sequence
from typing import Any, Protocol

from games.constants import AVATAR_SEED_PATTERN, AVATAR_STYLES
from rooms.models_types import Avatar, Profile, RoomError

SEED_RE = re.compile(AVATAR_SEED_PATTERN)
SEED_BYTES = 4  # 8 hex characters
MAX_ATTEMPTS = 20


class AvatarRng(Protocol):
    """Source of randomness for avatars (injectable so tests can control it)."""

    def choice(self, options: Sequence[str]) -> str: ...

    def token_hex(self, nbytes: int) -> str: ...


class SystemAvatarRng:
    """Production source: the `secrets` module."""

    def choice(self, options: Sequence[str]) -> str:
        return secrets.choice(options)

    def token_hex(self, nbytes: int) -> str:
        return secrets.token_hex(nbytes)


class SeededAvatarRng:
    """Deterministic source for tests."""

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def choice(self, options: Sequence[str]) -> str:
        return self._rng.choice(options)

    def token_hex(self, nbytes: int) -> str:
        return self._rng.getrandbits(8 * nbytes).to_bytes(nbytes, "big").hex()


def validate_avatar(raw: Any) -> Avatar:
    """Accept only {style in AVATAR_STYLES, seed matching AVATAR_SEED_PATTERN}."""
    if not isinstance(raw, dict):
        raise RoomError("INVALID_ACTION", "Avatar must be an object with style and seed.")
    style, seed = raw.get("style"), raw.get("seed")
    if style not in AVATAR_STYLES:
        raise RoomError("INVALID_ACTION", "Unknown avatar style.")
    if not isinstance(seed, str) or not SEED_RE.fullmatch(seed):
        raise RoomError("INVALID_ACTION", "Avatar seed is invalid.")
    return Avatar(style=style, seed=seed)


def assign_avatar(profile: Profile, rng: AvatarRng, *, taken: Collection[Avatar] = ()) -> Avatar:
    """The avatar for a new seat.

    A registered account keeps its saved avatar in every room (even if another seat has
    it). A guest gets a random style and seed, ignoring `profile.avatar`, never equal to
    one in `taken` (the room's other seats).
    """
    if profile.user_id is not None and profile.avatar is not None:
        return profile.avatar
    for _ in range(MAX_ATTEMPTS):
        candidate = {"style": rng.choice(AVATAR_STYLES), "seed": rng.token_hex(SEED_BYTES)}
        avatar = validate_avatar(candidate)
        if avatar not in taken:
            return avatar
    raise RuntimeError("Could not assign a unique avatar.")
