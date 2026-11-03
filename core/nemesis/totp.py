"""RFC 6238 TOTP (SHA-1, 30-second steps, 6 digits) and one-time backup codes, stdlib only."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

from django.conf import settings

STEP_S = 30
DIGITS = 6
WINDOW = 1  # steps accepted either side of now
SECRET_BYTES = 20
BACKUP_CODES = 10
BACKUP_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
BACKUP_LENGTH = 10
ISSUER = "Boredom"


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    return base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)


def code_at(secret: str, step: int) -> str:
    """The HOTP value for one time step (RFC 4226 dynamic truncation)."""
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_S)


def match_step(secret: str, code: str, now: float | None = None) -> int | None:
    """The time step `code` belongs to (now ± WINDOW), or None."""
    code = "".join(code.split()) if isinstance(code, str) else ""
    if len(code) != DIGITS or not code.isdigit():
        return None
    step = current_step(now)
    for candidate in range(step - WINDOW, step + WINDOW + 1):
        if hmac.compare_digest(code_at(secret, candidate), code):
            return candidate
    return None


def otpauth_uri(secret: str, account: str) -> str:
    label = quote(f"{ISSUER}:{account}")
    query = urlencode({"secret": secret, "issuer": ISSUER, "digits": DIGITS, "period": STEP_S})
    return f"otpauth://totp/{label}?{query}"


def hash_backup(code: str) -> str:
    normalized = "".join(code.split()).lower().replace("-", "")
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, normalized.encode(), hashlib.sha256).hexdigest()


def new_backup_codes() -> list[str]:
    return [
        "".join(secrets.choice(BACKUP_ALPHABET) for _ in range(BACKUP_LENGTH))
        for _ in range(BACKUP_CODES)
    ]
