"""Player money actions: deposits, payout destination, withdrawals, limits and self-exclusion.

Every check happens here, on the server. Balances move only through nemesis.ledger; each
posting has a fixed idempotency key per request, so a retried action never moves money twice.
Deposits, limits and payment details need an ACTIVE profile; withdrawals, the payout
destination, limits and taking a break also work while Nemesis is off or the player excluded.
"""

import re
import secrets
from datetime import datetime, timedelta
from typing import Any

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts.me import iso
from analytics.recorder import recorder
from games.constants import (
    DEPOSIT_30D_LIMIT,
    DEPOSIT_DAILY_LIMIT,
    DEPOSIT_MAX,
    DEPOSIT_MIN,
    DEPOSIT_REQUEST_TTL_MIN,
    LIMIT_RAISE_DELAY_HOURS,
    PAYMENT_NETWORKS,
    PAYOUT_CHANGE_DELAY_HOURS,
    SELF_EXCLUSION_DAYS,
    TAG_ALPHABET,
    WITHDRAW_DAILY_CAP,
    WITHDRAW_FIRST_DELAY_HOURS,
    WITHDRAW_MIN,
)
from nemesis import ledger, services
from nemesis.errors import NemesisError
from nemesis.ids import NAME_RE
from nemesis.models import (
    DepositRequest,
    LedgerAccount,
    MerchantDetails,
    NemesisProfile,
    PayoutMethod,
    WithdrawalRequest,
)

Kind = LedgerAccount.Kind
DStatus = DepositRequest.Status
WStatus = WithdrawalRequest.Status
OPEN_DEPOSIT = [DStatus.AWAITING_PAYMENT, DStatus.PENDING_REVIEW]
COUNTED_DEPOSIT = [*OPEN_DEPOSIT, DStatus.APPROVED]
COUNTED_WITHDRAWAL = [WStatus.PENDING_REVIEW, WStatus.APPROVED, WStatus.PAID]
REFERENCE_CHARS = 6
HISTORY_MAX = 50
PHONE_RE = re.compile(r"^\d{9,15}$")
ACCOUNT_RE = re.compile(r"^[A-Z0-9]{6,30}$")
PAYMENT_REF_RE = re.compile(r"^[A-Z0-9]{4,64}$")
BANK_NETWORK = "Bank transfer"


def _amount(raw: Any, field: str = "amount") -> int:
    if not isinstance(raw, int) or isinstance(raw, bool) or raw <= 0:
        raise NemesisError("INVALID_INPUT", "Enter an amount.", {field: "Whole pesewas only."})
    return raw


def _locked_profile(user: User) -> NemesisProfile:
    return NemesisProfile.objects.select_for_update().get_or_create(user=user)[0]


def _require_active(profile: NemesisProfile) -> None:
    if not profile.active:
        raise NemesisError("NOT_ACTIVE", "Turn on Nemesis first.")


def apply_due_raise(profile: NemesisProfile, now: datetime) -> None:
    """Move a pending limit raise whose time has come into the player's limits (saved)."""
    raise_ = profile.pending_limit_raise
    if not raise_ or not services._due(raise_, now):
        return
    if raise_.get("depositDailyLimit") is not None:
        profile.deposit_daily_limit = raise_["depositDailyLimit"]
    if raise_.get("deposit30dLimit") is not None:
        profile.deposit_30d_limit = raise_["deposit30dLimit"]
    profile.pending_limit_raise = None
    profile.save(update_fields=["deposit_daily_limit", "deposit_30d_limit", "pending_limit_raise"])


# ----- deposits --------------------------------------------------------------------------


def merchant_payload(m: MerchantDetails) -> dict[str, Any]:
    return {
        "method": m.method,
        "network": m.network,
        "number": m.number,
        "accountName": m.account_name,
    }


def payment_details(user: User) -> dict[str, Any]:
    profile = services.profile_of(user)
    if profile is None or not profile.active:
        raise NemesisError("NOT_ACTIVE", "Turn on Nemesis first.")
    merchant = MerchantDetails.objects.filter(active=True).first()
    if merchant is None:
        raise NemesisError("FEATURE_DISABLED", "Deposits are not available right now.")
    return merchant_payload(merchant)


def expire_deposits(now: datetime | None = None, user: User | None = None) -> int:
    """awaiting_payment requests past their expiry become expired."""
    rows = DepositRequest.objects.filter(
        status=DStatus.AWAITING_PAYMENT, expires_at__lte=now or timezone.now()
    )
    if user is not None:
        rows = rows.filter(user=user)
    return rows.update(status=DStatus.EXPIRED)


def deposited_since(user: User, since: datetime) -> int:
    """Deposits that count against limits: approved (received) and open (requested)."""
    total = DepositRequest.objects.filter(
        user=user, status__in=COUNTED_DEPOSIT, created_at__gte=since
    ).aggregate(s=Sum(Coalesce("amount_received", "amount_requested")))["s"]
    return total or 0


def deposit_remaining(user: User, profile: NemesisProfile, now: datetime) -> int:
    daily, thirty = services.effective_limits(profile, now)
    day = daily - deposited_since(user, now - timedelta(days=1))
    month = thirty - deposited_since(user, now - timedelta(days=30))
    return max(0, min(day, month))


def _new_reference() -> str:
    return "NEM-" + "".join(secrets.choice(TAG_ALPHABET) for _ in range(REFERENCE_CHARS))


def deposit_row(d: DepositRequest) -> dict[str, Any]:
    return {
        "id": d.pk,
        "reference": d.reference,
        "amount": d.amount_requested,
        "amountReceived": d.amount_received,
        "status": d.status,
        "paymentDetails": d.merchant_snapshot,
        "paymentRef": d.payment_ref,
        "senderNumber": d.sender_number,
        "createdAt": iso(d.created_at),
        "expiresAt": iso(d.expires_at),
        "submittedAt": iso(d.submitted_at) if d.submitted_at else None,
        "rejectReason": d.reject_reason or None,
    }


def create_deposit(user: User, body: dict[str, Any]) -> dict[str, Any]:
    amount = _amount(body.get("amount"))
    now = timezone.now()
    with transaction.atomic():
        profile = _locked_profile(user)
        _require_active(profile)
        if services.excluded(profile, now):
            raise NemesisError("EXCLUDED", "You are taking a break.")
        if not services.flags().deposits_enabled:
            raise NemesisError("FEATURE_DISABLED", "Deposits are paused right now.")
        if not DEPOSIT_MIN <= amount <= DEPOSIT_MAX:
            raise NemesisError(
                "INVALID_INPUT",
                "Amount out of range.",
                {"amount": f"Between {DEPOSIT_MIN} and {DEPOSIT_MAX}."},
            )
        expire_deposits(now, user)
        open_request = DepositRequest.objects.filter(user=user, status__in=OPEN_DEPOSIT).first()
        if open_request is not None:
            raise NemesisError(
                "DEPOSIT_OPEN", "You already have an open deposit.", extra={"id": open_request.pk}
            )
        apply_due_raise(profile, now)
        remaining = deposit_remaining(user, profile, now)
        if amount > remaining:
            raise NemesisError(
                "LIMIT_REACHED", "That is over your deposit limit.", extra={"remaining": remaining}
            )
        merchant = MerchantDetails.objects.filter(active=True).first()
        if merchant is None:
            raise NemesisError("FEATURE_DISABLED", "Deposits are not available right now.")
        for _ in range(10):
            try:
                with transaction.atomic():
                    deposit = DepositRequest.objects.create(
                        user=user,
                        reference=_new_reference(),
                        amount_requested=amount,
                        merchant_snapshot=merchant_payload(merchant),
                        expires_at=now + timedelta(minutes=DEPOSIT_REQUEST_TTL_MIN),
                    )
                break
            except IntegrityError:  # reference taken (one open request is held by the lock)
                continue
        else:
            raise NemesisError("INVALID_STATE", "Try again.")
    return deposit_row(deposit)


def _own_deposit(user: User, deposit_id: int) -> DepositRequest:
    d = DepositRequest.objects.select_for_update().filter(pk=deposit_id, user=user).first()
    if d is None:
        raise NemesisError("REQUEST_NOT_FOUND", "No such deposit.")
    return d


def normalize_ref(raw: Any) -> str:
    """Uppercase with spaces and punctuation removed."""
    return re.sub(r"[^A-Z0-9]", "", raw.upper()) if isinstance(raw, str) else ""


def normalize_phone(raw: Any) -> str:
    digits = re.sub(r"[\s()+-]", "", raw) if isinstance(raw, str) else ""
    return digits if PHONE_RE.match(digits) else ""


def submit_deposit(user: User, deposit_id: int, body: dict[str, Any]) -> dict[str, Any]:
    """The player's payment transaction ID and sender number: moves to pending_review."""
    ref = normalize_ref(body.get("paymentRef"))
    sender = normalize_phone(body.get("senderNumber"))
    errors = {}
    if not PAYMENT_REF_RE.match(ref):
        errors["paymentRef"] = "Enter the transaction ID from your payment."
    if not sender:
        errors["senderNumber"] = "Enter the number you paid from."
    if errors:
        raise NemesisError("INVALID_INPUT", "Some fields need fixing.", errors)
    now = timezone.now()
    with transaction.atomic():
        d = _own_deposit(user, deposit_id)
        if (
            d.status == DStatus.PENDING_REVIEW
            and d.payment_ref == ref
            and d.sender_number == sender
        ):
            return deposit_row(d)  # the same submission again (a network retry)
        if d.status == DStatus.AWAITING_PAYMENT and d.expires_at <= now:
            d.status = DStatus.EXPIRED
            d.save(update_fields=["status"])
            return deposit_row(d)
        if d.status != DStatus.AWAITING_PAYMENT:
            raise NemesisError("INVALID_STATE", "This deposit can no longer be changed.")
        taken = DepositRequest.objects.filter(
            payment_ref=ref, status__in=[DStatus.PENDING_REVIEW, DStatus.APPROVED]
        ).exists()
        if taken:
            raise NemesisError("DUPLICATE_REFERENCE", "That transaction ID was already used.")
        d.payment_ref, d.sender_number = ref, sender
        d.status, d.submitted_at = DStatus.PENDING_REVIEW, now
        try:
            with transaction.atomic():
                d.save()
        except IntegrityError:
            raise NemesisError(
                "DUPLICATE_REFERENCE", "That transaction ID was already used."
            ) from None
    recorder.record_event("deposit_submitted", user_id=user.pk)
    return deposit_row(d)


def cancel_deposit(user: User, deposit_id: int) -> dict[str, Any]:
    with transaction.atomic():
        d = _own_deposit(user, deposit_id)
        if d.status == DStatus.CANCELLED:
            return deposit_row(d)
        if d.status != DStatus.AWAITING_PAYMENT:
            raise NemesisError("INVALID_STATE", "Only an unpaid deposit can be cancelled.")
        d.status = DStatus.CANCELLED
        d.save(update_fields=["status"])
    return deposit_row(d)


def deposits(user: User) -> dict[str, Any]:
    expire_deposits(user=user)
    rows = DepositRequest.objects.filter(user=user).order_by("-created_at", "-pk")[:HISTORY_MAX]
    items = [deposit_row(d) for d in rows]
    open_row = next((r for r in items if r["status"] in OPEN_DEPOSIT), None)
    return {"deposits": items, "open": open_row}


# ----- payout destination ----------------------------------------------------------------


def set_payout(user: User, body: dict[str, Any]) -> dict[str, Any]:
    """Needs the account password. The first destination is effective at once (the first
    withdrawal still waits WITHDRAW_FIRST_DELAY_HOURS); a change waits PAYOUT_CHANGE_DELAY_HOURS
    and leaves existing requests alone."""
    password = body.get("password")
    if not isinstance(password, str) or not user.check_password(password):
        raise NemesisError("INVALID_INPUT", "Wrong password.", {"password": "Wrong password."})
    method, network = body.get("method"), body.get("network")
    errors = {}
    if method not in PayoutMethod.values:
        errors["method"] = "Choose a payout method."
    elif network not in PAYMENT_NETWORKS or (network == BANK_NETWORK) != (
        method == PayoutMethod.BANK
    ):
        errors["network"] = "Choose a network."
    if method == PayoutMethod.BANK:
        number = normalize_ref(body.get("number"))
        valid = bool(ACCOUNT_RE.match(number))
    else:
        number = normalize_phone(body.get("number"))
        valid = bool(number)
    if not valid:
        errors["number"] = "Enter the number."
    name = (
        " ".join(body.get("accountName", "").split())
        if isinstance(body.get("accountName"), str)
        else ""
    )
    if not (2 <= len(name) <= 100) or not NAME_RE.match(name):
        errors["accountName"] = "Enter the account name."
    if errors:
        raise NemesisError("INVALID_INPUT", "Some fields need fixing.", errors)
    now = timezone.now()
    with transaction.atomic():
        profile = _locked_profile(user)
        same = (
            profile.payout_method,
            profile.payout_network,
            profile.payout_number,
            profile.payout_account_name,
        ) == (method, network, number, name)
        if not same:
            first = not profile.payout_number
            profile.payout_method, profile.payout_network = method, network
            profile.payout_number, profile.payout_account_name = number, name
            profile.payout_effective_at = (
                now if first else now + timedelta(hours=PAYOUT_CHANGE_DELAY_HOURS)
            )
            profile.save()
    return {"payout": services.payout_payload(profile, now)}


# ----- withdrawals -----------------------------------------------------------------------


def withdrawal_row(w: WithdrawalRequest) -> dict[str, Any]:
    snap = w.payout_snapshot or {}
    return {
        "id": w.pk,
        "amount": w.amount,
        "status": w.status,
        "createdAt": iso(w.created_at),
        "eligibleAt": iso(w.eligible_at),
        "payout": {
            "method": snap.get("method"),
            "network": snap.get("network"),
            "number": services.mask_number(snap.get("number", "")),
            "accountName": snap.get("accountName"),
        },
        "payoutReference": w.payout_reference if w.status == WStatus.PAID else None,
        "paidAt": iso(w.paid_at) if w.paid_at else None,
        "rejectReason": w.reject_reason or None,
    }


def withdrawn_since(user: User, since: datetime) -> int:
    total = WithdrawalRequest.objects.filter(
        user=user, status__in=COUNTED_WITHDRAWAL, created_at__gte=since
    ).aggregate(s=Sum("amount"))["s"]
    return total or 0


def create_withdrawal(user: User, body: dict[str, Any]) -> dict[str, Any]:
    amount = _amount(body.get("amount"))
    now = timezone.now()
    with transaction.atomic():
        profile = _locked_profile(user)
        if not services.flags().withdrawals_enabled:
            raise NemesisError("FEATURE_DISABLED", "Withdrawals are paused right now.")
        if not profile.payout_number:
            raise NemesisError("PAYOUT_NOT_SET", "Add where to send your money first.")
        if profile.payout_effective_at is None or profile.payout_effective_at > now:
            raise NemesisError(
                "PAYOUT_PENDING",
                "Your new payout destination is not active yet.",
                extra={"effectiveAt": iso(profile.payout_effective_at or now)},
            )
        if amount < WITHDRAW_MIN:
            raise NemesisError(
                "INVALID_INPUT", "Amount too small.", {"amount": f"At least {WITHDRAW_MIN}."}
            )
        if WithdrawalRequest.objects.filter(user=user, status=WStatus.PENDING_REVIEW).exists():
            raise NemesisError("WITHDRAWAL_PENDING", "You already have a withdrawal waiting.")
        remaining = max(0, WITHDRAW_DAILY_CAP - withdrawn_since(user, now - timedelta(days=1)))
        if amount > remaining:
            raise NemesisError(
                "LIMIT_REACHED", "That is over the daily limit.", extra={"remaining": remaining}
            )
        first = WithdrawalRequest.objects.filter(user=user).order_by("created_at").first()
        start = first.created_at if first else now
        eligible_at = max(now, start + timedelta(hours=WITHDRAW_FIRST_DELAY_HOURS))
        w = WithdrawalRequest.objects.create(
            user=user,
            amount=amount,
            eligible_at=eligible_at,
            payout_snapshot={
                "method": profile.payout_method,
                "network": profile.payout_network,
                "number": profile.payout_number,
                "accountName": profile.payout_account_name,
            },
        )
        w.ledger_tx = ledger.post_transaction(
            "withdrawal_hold",
            f"withdrawal:{w.pk}:hold",
            [
                (ledger.account(Kind.USER, user), -amount),
                (ledger.account(Kind.WITHDRAWAL_HOLD, user), amount),
            ],
        )
        w.save(update_fields=["ledger_tx"])
    recorder.record_event("withdrawal_requested", user_id=user.pk)
    return withdrawal_row(w)


def refund_withdrawal(w: WithdrawalRequest, status: str) -> None:
    """Return a locked, unpaid request's funds from the hold (cancel or reject)."""
    assert w.user is not None
    w.settle_tx = ledger.post_transaction(
        "withdrawal_refund",
        f"withdrawal:{w.pk}:refund",
        [
            (ledger.account(Kind.WITHDRAWAL_HOLD, w.user), -w.amount),
            (ledger.account(Kind.USER, w.user), w.amount),
        ],
    )
    w.status = status
    w.save(update_fields=["settle_tx", "status"])


def cancel_withdrawal(user: User, withdrawal_id: int) -> dict[str, Any]:
    with transaction.atomic():
        w = (
            WithdrawalRequest.objects.select_for_update()
            .select_related("user")
            .filter(pk=withdrawal_id, user=user)
            .first()
        )
        if w is None:
            raise NemesisError("REQUEST_NOT_FOUND", "No such withdrawal.")
        if w.status == WStatus.CANCELLED:
            return withdrawal_row(w)
        if w.status != WStatus.PENDING_REVIEW:
            raise NemesisError("INVALID_STATE", "This withdrawal can no longer be cancelled.")
        refund_withdrawal(w, WStatus.CANCELLED)
    return withdrawal_row(w)


def withdrawals(user: User) -> dict[str, Any]:
    rows = WithdrawalRequest.objects.filter(user=user).order_by("-created_at", "-pk")
    return {"withdrawals": [withdrawal_row(w) for w in rows[:HISTORY_MAX]]}


# ----- limits and self-exclusion ---------------------------------------------------------


def _limit(raw: Any, field: str, maximum: int, errors: dict[str, str]) -> int | None:
    if not isinstance(raw, int) or isinstance(raw, bool) or not DEPOSIT_MIN <= raw <= maximum:
        errors[field] = f"Between {DEPOSIT_MIN} and {maximum}."
        return None
    return raw


def set_limits(user: User, body: dict[str, Any]) -> dict[str, Any]:
    """Lowering applies now; raising waits LIMIT_RAISE_DELAY_HOURS. Never above the platform."""
    errors: dict[str, str] = {}
    daily = _limit(body.get("depositDailyLimit"), "depositDailyLimit", DEPOSIT_DAILY_LIMIT, errors)
    thirty = _limit(body.get("deposit30dLimit"), "deposit30dLimit", DEPOSIT_30D_LIMIT, errors)
    if daily is not None and thirty is not None and daily > thirty:
        errors["depositDailyLimit"] = "Cannot be above the 30-day limit."
    if errors:
        raise NemesisError("INVALID_INPUT", "Some fields need fixing.", errors)
    now = timezone.now()
    with transaction.atomic():
        profile = _locked_profile(user)
        apply_due_raise(profile, now)
        cur_daily, cur_thirty = services.effective_limits(profile, now)
        pending: dict[str, Any] = {}
        if daily <= cur_daily:
            profile.deposit_daily_limit = daily
        else:
            pending["depositDailyLimit"] = daily
        if thirty <= cur_thirty:
            profile.deposit_30d_limit = thirty
        else:
            pending["deposit30dLimit"] = thirty
        if pending:
            pending["effectiveAt"] = iso(now + timedelta(hours=LIMIT_RAISE_DELAY_HOURS))
        profile.pending_limit_raise = pending or None
        profile.save()
    return services.wallet(user)["limits"]


def exclude(user: User, body: dict[str, Any]) -> dict[str, Any]:
    """Start a break now. A temporary break can only be lengthened; permanent is final."""
    days = body.get("days")
    if isinstance(days, bool) or days not in SELF_EXCLUSION_DAYS:
        raise NemesisError("INVALID_INPUT", "Choose how long.", {"days": "7, 30 or permanent."})
    now = timezone.now()
    with transaction.atomic():
        profile = _locked_profile(user)
        if days == "permanent":
            profile.excluded_permanent = True
        else:
            until = now + timedelta(days=days)
            if profile.excluded_until is None or profile.excluded_until < until:
                profile.excluded_until = until
        profile.save(update_fields=["excluded_permanent", "excluded_until"])
    return services.exclusion_payload(profile, now)


def open_money(user: User) -> bool:
    """Funds or open requests that block deleting the account (HAS_FUNDS)."""
    if LedgerAccount.objects.filter(user=user).exclude(balance=0).exists():
        return True
    if DepositRequest.objects.filter(user=user, status__in=OPEN_DEPOSIT).exists():
        return True
    if WithdrawalRequest.objects.filter(
        Q(user=user), Q(status__in=[WStatus.PENDING_REVIEW, WStatus.APPROVED])
    ).exists():
        return True
    return services.has_open_matches(user)
