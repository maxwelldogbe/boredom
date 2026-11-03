"""Nemesis reads shared by the player API and the staff tools. Money moves only in ledger.py."""

import math
from datetime import datetime, timedelta
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.me import iso
from accounts.models import PlayerStats
from analytics.recorder import recorder
from games.constants import (
    CURRENCY,
    DEPOSIT_30D_LIMIT,
    DEPOSIT_DAILY_LIMIT,
    DEPOSIT_MAX,
    DEPOSIT_MIN,
    ID_IMAGE_RETENTION_DAYS,
    MINOR_UNIT,
    NEMESIS_MIN_ACCOUNT_AGE_HOURS,
    NEMESIS_MIN_GAMES,
    NEMESIS_RULES_VERSION,
    WITHDRAW_DAILY_CAP,
    WITHDRAW_MIN,
)
from nemesis import ids, ledger
from nemesis.errors import NemesisError
from nemesis.models import DepositRequest, LedgerAccount, NemesisProfile, PlatformFlags

FLAGS_PK = 1


def flags() -> PlatformFlags:
    """The single PlatformFlags row, created with its defaults on first use."""
    return PlatformFlags.objects.get_or_create(pk=FLAGS_PK)[0]


def flags_payload(row: PlatformFlags | None = None) -> dict[str, bool]:
    row = row or flags()
    return {
        "depositsEnabled": row.deposits_enabled,
        "withdrawalsEnabled": row.withdrawals_enabled,
        "stakingEnabled": row.staking_enabled,
    }


def profile_of(user: User) -> NemesisProfile | None:
    return NemesisProfile.objects.filter(user=user).first()


def mask_number(number: str) -> str:
    """Show only the last 3 characters of a phone or account number."""
    return f"•••{number[-3:]}" if number else ""


def effective_limits(profile: NemesisProfile | None, now: datetime) -> tuple[int, int]:
    """The player's (daily, 30-day) deposit limits now, a due pending raise included."""
    daily = DEPOSIT_DAILY_LIMIT
    thirty = DEPOSIT_30D_LIMIT
    if profile is None:
        return daily, thirty
    if profile.deposit_daily_limit is not None:
        daily = min(daily, profile.deposit_daily_limit)
    if profile.deposit_30d_limit is not None:
        thirty = min(thirty, profile.deposit_30d_limit)
    raise_ = profile.pending_limit_raise
    if raise_ and _due(raise_, now):
        daily = min(DEPOSIT_DAILY_LIMIT, raise_.get("depositDailyLimit") or DEPOSIT_DAILY_LIMIT)
        thirty = min(DEPOSIT_30D_LIMIT, raise_.get("deposit30dLimit") or DEPOSIT_30D_LIMIT)
    return daily, thirty


def _due(raise_: dict[str, Any], now: datetime) -> bool:
    at = parse_datetime(raise_.get("effectiveAt") or "")
    return at is not None and at <= now


def excluded(profile: NemesisProfile | None, now: datetime) -> bool:
    if profile is None:
        return False
    return profile.excluded_permanent or bool(
        profile.excluded_until and profile.excluded_until > now
    )


def exclusion_payload(profile: NemesisProfile | None, now: datetime) -> dict[str, Any]:
    active = excluded(profile, now)
    until = profile.excluded_until if profile and active else None
    return {
        "active": active,
        "permanent": bool(profile and profile.excluded_permanent),
        "until": iso(until) if until else None,
    }


def payout_payload(profile: NemesisProfile | None, now: datetime) -> dict[str, Any] | None:
    if profile is None or not profile.payout_number:
        return None
    at = profile.payout_effective_at
    return {
        "method": profile.payout_method,
        "network": profile.payout_network,
        "number": mask_number(profile.payout_number),
        "accountName": profile.payout_account_name,
        "effectiveAt": iso(at) if at else None,
        "effective": bool(at and at <= now),
    }


def wallet(user: User) -> dict[str, Any]:
    """GET /api/wallet: balances, limits, exclusion, payout (masked) and flags."""
    now = timezone.now()
    profile = profile_of(user)
    daily, thirty = effective_limits(profile, now)
    pending = profile.pending_limit_raise if profile else None
    return {
        "currency": CURRENCY,
        "minorUnit": MINOR_UNIT,
        "balance": ledger.balance(LedgerAccount.Kind.USER, user),
        "held": ledger.balance(LedgerAccount.Kind.WITHDRAWAL_HOLD, user),
        "limits": {
            "platform": {
                "depositMin": DEPOSIT_MIN,
                "depositMax": DEPOSIT_MAX,
                "depositDaily": DEPOSIT_DAILY_LIMIT,
                "deposit30d": DEPOSIT_30D_LIMIT,
                "withdrawMin": WITHDRAW_MIN,
                "withdrawDailyCap": WITHDRAW_DAILY_CAP,
            },
            "player": {"depositDaily": daily, "deposit30d": thirty},
            "pendingRaise": pending if pending and not _due(pending, now) else None,
        },
        "exclusion": exclusion_payload(profile, now),
        "payout": payout_payload(profile, now),
        "flags": flags_payload(),
    }


# ----- status and opt-in -----------------------------------------------------------------


def has_open_matches(user: User) -> bool:
    """Whether the player has a staked match in progress (filled in by Part 2)."""
    return False


def has_open_deposit(user: User) -> bool:
    return DepositRequest.objects.filter(
        user=user,
        status__in=[DepositRequest.Status.AWAITING_PAYMENT, DepositRequest.Status.PENDING_REVIEW],
    ).exists()


def eligibility(user: User, now: datetime) -> dict[str, Any]:
    ready_at = user.date_joined + timedelta(hours=NEMESIS_MIN_ACCOUNT_AGE_HOURS)
    hours_left = max(0, math.ceil((ready_at - now).total_seconds() / 3600))
    played = PlayerStats.objects.filter(user=user).aggregate(s=Sum("played"))["s"] or 0
    return {
        "accountAgeOk": ready_at <= now,
        "hoursLeft": hours_left,
        "gamesPlayed": played,
        "gamesNeeded": max(0, NEMESIS_MIN_GAMES - played),
        "idState": ids.id_state(user)["idState"],
    }


def status(user: User) -> dict[str, Any]:
    """GET /api/nemesis/status (while enabled)."""
    now = timezone.now()
    profile = profile_of(user)
    id_info = ids.id_state(user)
    return {
        "enabled": True,
        "active": bool(profile and profile.active),
        "rulesVersion": NEMESIS_RULES_VERSION,
        "eligibility": eligibility(user, now),
        "idState": id_info["idState"],
        "attemptsLeft": id_info["attemptsLeft"],
        "rejectionReason": id_info["rejectionReason"],
        "retentionDays": ID_IMAGE_RETENTION_DAYS,
        "excluded": excluded(profile, now),
    }


def activate(user: User, body: dict[str, Any]) -> dict[str, Any]:
    """Turn Nemesis on. No credit of any kind is given."""
    now = timezone.now()
    with transaction.atomic():
        profile = NemesisProfile.objects.select_for_update().get_or_create(user=user)[0]
        if profile.active:
            raise NemesisError("ALREADY_ACTIVE", "Nemesis is already on.")
        if excluded(profile, now):
            raise NemesisError("EXCLUDED", "You are taking a break.")
        info = eligibility(user, now)
        if info["idState"] != "approved":
            raise NemesisError("ID_REQUIRED", "Verify your age first.")
        if not info["accountAgeOk"] or info["gamesNeeded"] > 0:
            raise NemesisError(
                "NOT_ELIGIBLE", "You are not eligible yet.", extra={"eligibility": info}
            )
        fields = {}
        if body.get("confirmAge") is not True:
            fields["confirmAge"] = "Confirm you are 18 or older."
        if body.get("acceptRules") is not True:
            fields["acceptRules"] = "Accept the rules."
        if body.get("rulesVersion") != NEMESIS_RULES_VERSION:
            fields["rulesVersion"] = "The rules changed. Read them again."
        if fields:
            raise NemesisError("INVALID_INPUT", "Some fields need fixing.", fields)
        profile.active = True
        profile.activated_at = profile.age_confirmed_at = now
        profile.rules_version = NEMESIS_RULES_VERSION
        profile.save()
    recorder.record_event("nemesis_activated", user_id=user.pk)
    return status(user)


def deactivate(user: User) -> dict[str, Any]:
    """Turn Nemesis off at once. Balance, history and withdrawals stay available."""
    with transaction.atomic():
        profile = NemesisProfile.objects.select_for_update().filter(user=user).first()
        if profile is None or not profile.active:
            raise NemesisError("NOT_ACTIVE", "Nemesis is already off.")
        if has_open_matches(user):
            raise NemesisError("INVALID_STATE", "Finish your open matches first.")
        if has_open_deposit(user):
            raise NemesisError("DEPOSIT_OPEN", "Finish or cancel your open deposit first.")
        profile.active = False
        profile.deactivated_at = timezone.now()
        profile.save(update_fields=["active", "deactivated_at"])
    recorder.record_event("nemesis_deactivated", user_id=user.pk)
    return status(user)
