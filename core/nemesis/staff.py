"""Staff two-factor state: enrolment, code checks (replay-safe), the 2FA session mark, step-up.

A staff session counts as two-factor only after a code was checked in it (dashboard login,
enrolment confirm). Money endpoints require that mark, so a password-only session (e.g. the
Django admin login) can never reach them.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from analytics.lockout import admin_lockout
from games.constants import STEP_UP_MINUTES
from nemesis import totp
from nemesis.errors import NemesisError
from nemesis.models import StaffSecurity

SESSION_KEY = "nemesis_2fa_user"
PERMISSIONS = (
    "review_ids",
    "review_deposits",
    "review_withdrawals",
    "adjust_balances",
    "edit_merchant",
    "edit_flags",
)


def perm(name: str) -> str:
    return f"nemesis.{name}"


def permissions_of(user: User) -> list[str]:
    return [p for p in PERMISSIONS if user.has_perm(perm(p))]


def security_of(user: User) -> StaffSecurity | None:
    return StaffSecurity.objects.filter(user=user).first()


def enrolled(user: User) -> bool:
    return StaffSecurity.objects.filter(user=user, enrolled_at__isnull=False).exists()


def session_verified(request: HttpRequest) -> bool:
    return request.session.get(SESSION_KEY) == request.user.pk


def mark_session(request: HttpRequest, user: User) -> None:
    request.session[SESSION_KEY] = user.pk


def lockout_key(request: HttpRequest, user: User) -> tuple[str, str]:
    return admin_lockout.key(request.META.get("REMOTE_ADDR") or "unknown", f"2fa:{user.pk}")


def check_code(user: User, code: object, *, allow_backup: bool, enrolling: bool = False) -> bool:
    """True if `code` is a fresh TOTP code (or an unused backup code, which is consumed).

    A TOTP code from a step already used is rejected (no replay within its step).
    """
    with transaction.atomic():
        sec = StaffSecurity.objects.select_for_update().filter(user=user).first()
        if sec is None or (sec.enrolled_at is None) != enrolling:
            return False
        step = totp.match_step(sec.totp_secret, code if isinstance(code, str) else "")
        if step is not None:
            if sec.last_totp_step is not None and step <= sec.last_totp_step:
                return False
            sec.last_totp_step = step
            sec.save(update_fields=["last_totp_step"])
            return True
        if allow_backup and isinstance(code, str) and code.strip():
            hashed = totp.hash_backup(code)
            if hashed in sec.backup_codes_hash:
                sec.backup_codes_hash = [h for h in sec.backup_codes_hash if h != hashed]
                sec.save(update_fields=["backup_codes_hash"])
                return True
    return False


def verify_with_lockout(
    request: HttpRequest, user: User, code: object, *, allow_backup: bool
) -> None:
    """check_code with the admin lockout (LOCKED after repeated failures, INVALID_CODE)."""
    key = lockout_key(request, user)
    if admin_lockout.locked(key):
        raise NemesisError("LOCKED", "Too many wrong codes. Try again later.")
    if not check_code(user, code, allow_backup=allow_backup):
        admin_lockout.failed(key)
        raise NemesisError("INVALID_CODE", "That code is not right.")
    admin_lockout.succeeded(key)


def setup(user: User) -> dict[str, str]:
    """Start (or restart, while not enrolled) enrolment with a new secret."""
    sec = security_of(user)
    if sec is not None and sec.enrolled_at is not None:
        raise NemesisError("INVALID_STATE", "Two-factor is already set up.")
    secret = totp.new_secret()
    StaffSecurity.objects.update_or_create(
        user=user, defaults={"totp_secret": secret, "last_totp_step": None}
    )
    return {"secret": secret, "otpauthUri": totp.otpauth_uri(secret, user.get_username())}


def confirm(request: HttpRequest, user: User, code: object) -> list[str]:
    """Finish enrolment with a code from the app; returns the backup codes (shown once)."""
    key = lockout_key(request, user)
    if admin_lockout.locked(key):
        raise NemesisError("LOCKED", "Too many wrong codes. Try again later.")
    if not check_code(user, code, allow_backup=False, enrolling=True):
        admin_lockout.failed(key)
        raise NemesisError("INVALID_CODE", "That code is not right.")
    admin_lockout.succeeded(key)
    codes = totp.new_backup_codes()
    StaffSecurity.objects.filter(user=user).update(
        enrolled_at=timezone.now(), backup_codes_hash=[totp.hash_backup(c) for c in codes]
    )
    mark_session(request, user)
    return codes


def step_up(request: HttpRequest, user: User, code: object) -> None:
    verify_with_lockout(request, user, code, allow_backup=False)
    StaffSecurity.objects.filter(user=user).update(last_step_up_at=timezone.now())


def stepped_up(user: User) -> bool:
    since = timezone.now() - timedelta(minutes=STEP_UP_MINUTES)
    return StaffSecurity.objects.filter(user=user, last_step_up_at__gte=since).exists()
