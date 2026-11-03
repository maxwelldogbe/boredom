"""Account recovery by SMS: confirming a phone number and resetting a forgotten password.

Codes are PHONE_CODE_LENGTH digits, kept only as an HMAC in the cache for
PHONE_CODE_TTL_MINUTES, with PHONE_CODE_MAX_TRIES tries; each number gets at most
PHONE_CODES_PER_HOUR codes. A profile's `phone` is set only once confirmed. After a reset,
tokens issued before `password_changed_at` stop working (token_revoked).
"""

import hashlib
import hmac
import re
import secrets
from typing import Any

from django.conf import settings
from django.core.cache import cache

from accounts.sms import send_sms
from accounts.tokens import token_issued_at
from games.constants import (
    PHONE_CODE_LENGTH,
    PHONE_CODE_MAX_TRIES,
    PHONE_CODE_TTL_MINUTES,
    PHONE_CODES_PER_HOUR,
    PHONE_DEFAULT_COUNTRY_CODE,
)

_SEPARATORS = re.compile(r"[\s\-().]")
VERIFY, RESET = "verify", "reset"


def normalize_phone(raw: Any) -> str | None:
    """Digits with the country code (233240000000), or None. A leading 0 means the default
    country (PHONE_DEFAULT_COUNTRY_CODE); + or 00 means the code is given."""
    if not isinstance(raw, str):
        return None
    text = _SEPARATORS.sub("", raw.strip())
    if text.startswith("+"):
        text = text[1:]
    elif text.startswith("00"):
        text = text[2:]
    elif text.startswith("0"):
        text = PHONE_DEFAULT_COUNTRY_CODE + text[1:]
    return text if text.isdigit() and 10 <= len(text) <= 15 else None


def mask_phone(phone: str | None) -> str | None:
    """ "+233•••••0000" (only the country code and the last 4 digits)."""
    if not phone:
        return None
    return f"+{phone[:3]}{'•' * max(0, len(phone) - 7)}{phone[-4:]}"


def _digest(code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()


def _key(purpose: str, user_id: int) -> str:
    return f"recovery:{purpose}:{user_id}"


def send_code(purpose: str, user_id: int, phone: str) -> bool:
    """Text a fresh code to `phone`; False when this number hit its hourly limit or SMS failed."""
    sent_key = f"recovery:sent:{phone}"
    cache.add(sent_key, 0, timeout=3600)
    try:
        count = cache.incr(sent_key)
    except ValueError:  # expired between add and incr
        cache.set(sent_key, 1, timeout=3600)
        count = 1
    if count > PHONE_CODES_PER_HOUR:
        return False
    code = f"{secrets.randbelow(10**PHONE_CODE_LENGTH):0{PHONE_CODE_LENGTH}d}"
    entry = {"digest": _digest(code), "tries": 0, "phone": phone}
    cache.set(_key(purpose, user_id), entry, timeout=PHONE_CODE_TTL_MINUTES * 60)
    message = (
        f"Your boredom code is {code}. It expires in {PHONE_CODE_TTL_MINUTES} minutes. "
        "Never share it with anyone."
    )
    return send_sms(phone, message, reference=f"{purpose}-{user_id}")


def check_code(purpose: str, user_id: int, code: Any) -> str | None:
    """The phone the code was sent to when `code` is right (the code is then used up), else
    None. Every wrong try counts; after PHONE_CODE_MAX_TRIES the code is gone."""
    key = _key(purpose, user_id)
    entry = cache.get(key)
    if entry is None or not isinstance(code, str):
        return None
    entry["tries"] += 1
    if not hmac.compare_digest(entry["digest"], _digest(code.strip())):
        if entry["tries"] >= PHONE_CODE_MAX_TRIES:
            cache.delete(key)
        else:
            cache.set(key, entry, timeout=PHONE_CODE_TTL_MINUTES * 60)
        return None
    cache.delete(key)
    return entry["phone"]


def token_revoked(password_changed_at: Any, token: Any) -> bool:
    """True for a token issued before the password last changed (signed out by a reset)."""
    if password_changed_at is None:
        return False
    issued = token_issued_at(token)
    return issued is None or issued < int(password_changed_at.timestamp())


# ----- staff-reviewed requests (players who never added a recovery number) -------------------

ANSWER_KEYS = ("nickname", "joined", "friend", "games", "note")


def clean_answers(raw: Any) -> dict[str, str]:
    """The player's answers, each trimmed to RECOVERY_ANSWER_MAX characters (others dropped)."""
    from games.constants import RECOVERY_ANSWER_MAX

    raw = raw if isinstance(raw, dict) else {}
    return {
        key: raw[key].strip()[:RECOVERY_ANSWER_MAX]
        for key in ANSWER_KEYS
        if isinstance(raw.get(key), str) and raw[key].strip()
    }


def submit_request(username: str, phone: str, answers: dict[str, str]) -> None:
    """Store a request for staff. One open request per account: a new one replaces it."""
    from django.contrib.auth.models import User

    from accounts.models import RecoveryRequest

    user = User.objects.filter(username__iexact=username, is_active=True).first()
    if user is not None:
        RecoveryRequest.objects.filter(user=user, status=RecoveryRequest.Status.PENDING).update(
            status=RecoveryRequest.Status.REJECTED, review_note="Replaced by a newer request."
        )
    RecoveryRequest.objects.create(user=user, username=username, phone=phone, answers=answers)


def approve_request(request_id: int, staff: Any, note: str) -> str | None:
    """Text a code to the request's phone. None when done; else a reason it could not be."""
    from django.utils import timezone

    from accounts.models import Profile, RecoveryRequest
    from games.constants import RECOVERY_CODE_HOURS

    req = RecoveryRequest.objects.filter(pk=request_id).first()
    if req is None or req.status != RecoveryRequest.Status.PENDING:
        return "This request was already handled."
    if req.user is None:
        return "No account has that username."
    if Profile.objects.filter(phone=req.phone).exclude(user=req.user).exists():
        return "That number is the recovery number of another account."
    code = f"{secrets.randbelow(10**PHONE_CODE_LENGTH):0{PHONE_CODE_LENGTH}d}"
    message = (
        f"Your boredom account recovery was approved. Your code is {code}. "
        f"It expires in {RECOVERY_CODE_HOURS} hours. Never share it with anyone."
    )
    if not send_sms(req.phone, message, reference=f"recovery-{req.pk}"):
        return "The SMS could not be sent. Try again later."
    now = timezone.now()
    req.status, req.reviewed_by, req.reviewed_at, req.review_note = (
        RecoveryRequest.Status.APPROVED,
        staff,
        now,
        note,
    )
    req.code_digest, req.code_tries = _digest(code), 0
    req.code_expires_at = now + timezone.timedelta(hours=RECOVERY_CODE_HOURS)
    req.save()
    return None


def reject_request(request_id: int, staff: Any, note: str) -> str | None:
    from django.utils import timezone

    from accounts.models import RecoveryRequest

    req = RecoveryRequest.objects.filter(pk=request_id).first()
    if req is None or req.status != RecoveryRequest.Status.PENDING:
        return "This request was already handled."
    req.status, req.reviewed_by, req.reviewed_at, req.review_note = (
        RecoveryRequest.Status.REJECTED,
        staff,
        timezone.now(),
        note,
    )
    req.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
    return None


def redeem_approved_code(user: Any, code: Any) -> str | None:
    """The phone of the user's approved request when `code` matches (the request is then
    completed), else None. Wrong tries count; after PHONE_CODE_MAX_TRIES the code is void."""
    from django.utils import timezone

    from accounts.models import RecoveryRequest

    req = (
        RecoveryRequest.objects.filter(user=user, status=RecoveryRequest.Status.APPROVED)
        .order_by("-reviewed_at")
        .first()
    )
    if req is None or not isinstance(code, str) or req.code_tries >= PHONE_CODE_MAX_TRIES:
        return None
    if req.code_expires_at is None or req.code_expires_at < timezone.now():
        return None
    if not hmac.compare_digest(req.code_digest, _digest(code.strip())):
        req.code_tries += 1
        req.save(update_fields=["code_tries"])
        return None
    req.status, req.code_digest = RecoveryRequest.Status.COMPLETED, ""
    req.save(update_fields=["status", "code_digest"])
    return req.phone
