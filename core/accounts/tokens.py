"""Stateless access tokens: HS256 JWTs signed with SECRET_KEY, valid AUTH_TOKEN_DAYS.

Claims are {sub: user id (string), exp, iat}. There is no server-side logout, but a password
reset makes older tokens invalid (accounts.recovery.token_revoked).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from django.conf import settings

from games.constants import AUTH_TOKEN_DAYS

ALGORITHM = "HS256"
TOKEN_MAX_CHARS = 2048


def issue_token(user_id: int, now: datetime | None = None) -> str:
    """A signed token for `user_id`, expiring AUTH_TOKEN_DAYS after `now`."""
    issued = now or datetime.now(UTC)
    claims = {"sub": str(user_id), "iat": issued, "exp": issued + timedelta(days=AUTH_TOKEN_DAYS)}
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=ALGORITHM)


def _claims(token: Any) -> dict[str, Any] | None:
    if not isinstance(token, str) or not 0 < len(token) <= TOKEN_MAX_CHARS:
        return None
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp", "iat"]},
        )
    except jwt.InvalidTokenError:
        return None


def token_issued_at(token: Any) -> int | None:
    """The `iat` (epoch seconds) of a valid token, or None."""
    claims = _claims(token)
    iat = claims.get("iat") if claims else None
    return int(iat) if isinstance(iat, int | float) else None


def user_id_from_token(token: Any) -> int | None:
    """The user id in a valid, unexpired token, or None for anything else."""
    claims = _claims(token)
    if claims is None:
        return None
    sub = claims["sub"]
    return int(sub) if isinstance(sub, str) and sub.isdigit() else None
