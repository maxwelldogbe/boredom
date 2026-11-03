"""Staff money decisions: deposits, withdrawals, adjustments, merchant details, flags, reports.

Each decision locks its row, checks the state, and posts to the ledger with a fixed key, so a
repeated or concurrent decision never moves money twice. Staff can never decide their own
requests. With DUAL_APPROVAL_ENABLED, large deposits and withdrawals and every adjustment,
merchant change and flag change need a second, different staff member.
"""

from datetime import date
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from analytics.recorder import recorder
from games.constants import DUAL_APPROVAL_THRESHOLD, PAYMENT_NETWORKS
from nemesis import ledger, services
from nemesis.errors import NemesisError
from nemesis.models import (
    AdjustmentRequest,
    DepositRequest,
    LedgerAccount,
    MerchantDetails,
    NemesisProfile,
    PayoutMethod,
    ReconciliationReport,
    WithdrawalRequest,
)
from nemesis.wallet import (
    ACCOUNT_RE,
    BANK_NETWORK,
    normalize_phone,
    normalize_ref,
    refund_withdrawal,
)

Kind = LedgerAccount.Kind
DStatus = DepositRequest.Status
WStatus = WithdrawalRequest.Status
AStatus = AdjustmentRequest.Status
REASON_MAX = 200
FLAG_FIELDS = {
    "depositsEnabled": "deposits_enabled",
    "withdrawalsEnabled": "withdrawals_enabled",
    "stakingEnabled": "staking_enabled",
}


def dual_enabled() -> bool:
    return bool(settings.DUAL_APPROVAL_ENABLED)


def _reason(raw: Any, field: str = "reason") -> str:
    text = " ".join(raw.split()) if isinstance(raw, str) else ""
    if not text or len(text) > REASON_MAX:
        raise NemesisError("INVALID_INPUT", "Give a reason.", {field: "Required."})
    return text


def _not_own(owner_id: int | None, staff: User) -> None:
    if owner_id is not None and owner_id == staff.pk:
        raise NemesisError("FORBIDDEN", "You cannot act on your own account.")


def _second_approver(first_id: int | None, staff: User) -> None:
    if first_id == staff.pk:
        raise NemesisError("FORBIDDEN", "A different staff member must give the second approval.")


# ----- deposits --------------------------------------------------------------------------


def _locked_deposit(deposit_id: int, staff: User) -> DepositRequest:
    d = (
        DepositRequest.objects.select_for_update()
        .select_related("user")
        .filter(pk=deposit_id)
        .first()
    )
    if d is None:
        raise NemesisError("REQUEST_NOT_FOUND", "No such deposit.")
    _not_own(d.user_id, staff)
    if d.status != DStatus.PENDING_REVIEW:
        raise NemesisError("INVALID_STATE", "This deposit is not waiting for review.")
    return d


def approve_deposit(deposit_id: int, staff: User, body: dict[str, Any]) -> DepositRequest:
    """Credit `receivedAmount` once the reviewer confirmed the payment in the receiving account.

    A different received amount needs a note and only that amount is credited.
    """
    received = body.get("receivedAmount")
    if not isinstance(received, int) or isinstance(received, bool) or received <= 0:
        raise NemesisError(
            "INVALID_INPUT", "Enter the amount received.", {"receivedAmount": "Required."}
        )
    if body.get("verifiedInAccount") is not True:
        raise NemesisError(
            "INVALID_INPUT",
            "Confirm you verified the payment in the receiving account.",
            {"verifiedInAccount": "Required."},
        )
    note = body.get("note")
    note = " ".join(note.split()) if isinstance(note, str) else ""
    if len(note) > REASON_MAX:
        raise NemesisError("INVALID_INPUT", "Note too long.", {"note": "Too long."})
    now = timezone.now()
    with transaction.atomic():
        d = _locked_deposit(deposit_id, staff)
        if received != d.amount_requested and not note:
            raise NemesisError(
                "INVALID_INPUT", "Explain the different amount.", {"note": "Required."}
            )
        if dual_enabled() and received >= DUAL_APPROVAL_THRESHOLD:
            if d.first_approved_by_id is None:
                d.first_approved_by, d.first_approved_at = staff, now
                d.amount_received, d.note = received, note
                d.save(
                    update_fields=[
                        "first_approved_by",
                        "first_approved_at",
                        "amount_received",
                        "note",
                    ]
                )
                return d
            _second_approver(d.first_approved_by_id, staff)
            if received != d.amount_received:
                raise NemesisError("INVALID_STATE", "The amount differs from the first approval.")
            note = d.note or note
        assert d.user is not None
        d.ledger_tx = ledger.post_transaction(
            "deposit",
            f"deposit:{d.pk}",
            [
                (ledger.account(Kind.EXTERNAL), -received),
                (ledger.account(Kind.USER, d.user), received),
            ],
            {"depositId": d.pk},
        )
        d.status, d.amount_received, d.note = DStatus.APPROVED, received, note
        d.reviewed_by, d.reviewed_at = staff, now
        d.save()
    recorder.record_event("deposit_approved", user_id=d.user_id)
    return d


def reject_deposit(deposit_id: int, staff: User, body: dict[str, Any]) -> DepositRequest:
    reason = _reason(body.get("reason"))
    with transaction.atomic():
        d = _locked_deposit(deposit_id, staff)
        d.status, d.reject_reason = DStatus.REJECTED, reason
        d.reviewed_by, d.reviewed_at = staff, timezone.now()
        d.save()
    recorder.record_event("deposit_rejected", user_id=d.user_id)
    return d


# ----- withdrawals -----------------------------------------------------------------------


def _locked_withdrawal(withdrawal_id: int, staff: User, *states: str) -> WithdrawalRequest:
    w = (
        WithdrawalRequest.objects.select_for_update()
        .select_related("user")
        .filter(pk=withdrawal_id)
        .first()
    )
    if w is None:
        raise NemesisError("REQUEST_NOT_FOUND", "No such withdrawal.")
    _not_own(w.user_id, staff)
    if w.status not in states:
        raise NemesisError("INVALID_STATE", "This withdrawal cannot do that now.")
    return w


def approve_withdrawal(withdrawal_id: int, staff: User) -> WithdrawalRequest:
    now = timezone.now()
    with transaction.atomic():
        w = _locked_withdrawal(withdrawal_id, staff, WStatus.PENDING_REVIEW)
        if w.eligible_at > now:
            raise NemesisError("INVALID_STATE", "This withdrawal is not eligible yet.")
        if dual_enabled() and w.amount >= DUAL_APPROVAL_THRESHOLD:
            if w.first_approved_by_id is None:
                w.first_approved_by, w.first_approved_at = staff, now
                w.save(update_fields=["first_approved_by", "first_approved_at"])
                return w
            _second_approver(w.first_approved_by_id, staff)
        w.status, w.reviewed_by, w.reviewed_at = WStatus.APPROVED, staff, now
        w.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    return w


def mark_paid(withdrawal_id: int, staff: User, body: dict[str, Any]) -> WithdrawalRequest:
    """After paying by hand: the held amount leaves to external."""
    reference = body.get("payoutReference")
    reference = reference.strip() if isinstance(reference, str) else ""
    if not reference or len(reference) > 64:
        raise NemesisError(
            "INVALID_INPUT", "Enter the payout reference.", {"payoutReference": "Required."}
        )
    with transaction.atomic():
        w = _locked_withdrawal(withdrawal_id, staff, WStatus.APPROVED)
        assert w.user is not None
        w.settle_tx = ledger.post_transaction(
            "withdrawal_paid",
            f"withdrawal:{w.pk}:paid",
            [
                (ledger.account(Kind.WITHDRAWAL_HOLD, w.user), -w.amount),
                (ledger.account(Kind.EXTERNAL), w.amount),
            ],
            {"withdrawalId": w.pk},
        )
        w.status, w.payout_reference = WStatus.PAID, reference
        w.paid_by, w.paid_at = staff, timezone.now()
        w.save()
    recorder.record_event("withdrawal_paid", user_id=w.user_id)
    return w


def reject_withdrawal(withdrawal_id: int, staff: User, body: dict[str, Any]) -> WithdrawalRequest:
    reason = _reason(body.get("reason"))
    with transaction.atomic():
        w = _locked_withdrawal(withdrawal_id, staff, WStatus.PENDING_REVIEW, WStatus.APPROVED)
        w.reject_reason, w.reviewed_by, w.reviewed_at = reason, staff, timezone.now()
        w.save(update_fields=["reject_reason", "reviewed_by", "reviewed_at"])
        refund_withdrawal(w, WStatus.REJECTED)
    return w


# ----- adjustments -----------------------------------------------------------------------


def _apply_adjustment(a: AdjustmentRequest, approver: User) -> None:
    """Post the correction between the user's own account and external (never escrow)."""
    assert a.user is not None
    a.ledger_tx = ledger.post_transaction(
        "adjustment",
        f"adjustment:{a.pk}",
        [(ledger.account(Kind.USER, a.user), a.amount), (ledger.account(Kind.EXTERNAL), -a.amount)],
        {"adjustmentId": a.pk},
    )
    a.status, a.approved_by, a.decided_at = AStatus.APPLIED, approver, timezone.now()
    a.save()


def propose_adjustment(staff: User, body: dict[str, Any]) -> AdjustmentRequest:
    amount = body.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount == 0:
        raise NemesisError("INVALID_INPUT", "Enter a nonzero amount.", {"amount": "Required."})
    reason = _reason(body.get("reason"))
    user = (
        User.objects.filter(pk=body.get("userId")).first()
        if isinstance(body.get("userId"), int)
        else None
    )
    if user is None:
        raise NemesisError("REQUEST_NOT_FOUND", "No such account.")
    _not_own(user.pk, staff)
    with transaction.atomic():
        a = AdjustmentRequest.objects.create(
            user=user, amount=amount, reason=reason, proposed_by=staff
        )
        if not dual_enabled():
            _apply_adjustment(a, staff)
    return a


def _locked_adjustment(adjustment_id: int, staff: User) -> AdjustmentRequest:
    a = (
        AdjustmentRequest.objects.select_for_update()
        .select_related("user")
        .filter(pk=adjustment_id)
        .first()
    )
    if a is None:
        raise NemesisError("REQUEST_NOT_FOUND", "No such adjustment.")
    _not_own(a.user_id, staff)
    if a.status != AStatus.PENDING:
        raise NemesisError("INVALID_STATE", "This adjustment was already decided.")
    return a


def approve_adjustment(adjustment_id: int, staff: User) -> AdjustmentRequest:
    with transaction.atomic():
        a = _locked_adjustment(adjustment_id, staff)
        _second_approver(a.proposed_by_id, staff)
        _apply_adjustment(a, staff)
    return a


def reject_adjustment(adjustment_id: int, staff: User) -> AdjustmentRequest:
    with transaction.atomic():
        a = _locked_adjustment(adjustment_id, staff)
        a.status, a.approved_by, a.decided_at = AStatus.REJECTED, staff, timezone.now()
        a.save()
    return a


# ----- merchant details ------------------------------------------------------------------


def _activate_merchant(m: MerchantDetails, approver: User) -> None:
    MerchantDetails.objects.filter(active=True).exclude(pk=m.pk).update(active=False)
    m.active, m.approved_by, m.activated_at = True, approver, timezone.now()
    m.save()


def propose_merchant(staff: User, body: dict[str, Any]) -> MerchantDetails:
    """A new version; active at once, or after a second staff member with dual approval.
    Open deposit requests keep the snapshot they were given."""
    method, network = body.get("method"), body.get("network")
    errors = {}
    if method not in PayoutMethod.values:
        errors["method"] = "Choose a method."
    elif network not in PAYMENT_NETWORKS or (network == BANK_NETWORK) != (
        method == PayoutMethod.BANK
    ):
        errors["network"] = "Choose a network."
    number = (
        normalize_ref(body.get("number"))
        if method == PayoutMethod.BANK
        else normalize_phone(body.get("number"))
    )
    if method == PayoutMethod.BANK and not ACCOUNT_RE.match(number):
        number = ""
    if not number:
        errors["number"] = "Enter the number."
    name = body.get("accountName")
    name = " ".join(name.split()) if isinstance(name, str) else ""
    if not 2 <= len(name) <= 100:
        errors["accountName"] = "Enter the account name."
    if errors:
        raise NemesisError("INVALID_INPUT", "Some fields need fixing.", errors)
    with transaction.atomic():
        m = MerchantDetails.objects.create(
            method=method, network=network, number=number, account_name=name, created_by=staff
        )
        if not dual_enabled():
            _activate_merchant(m, staff)
    return m


def approve_merchant(merchant_id: int, staff: User) -> MerchantDetails:
    with transaction.atomic():
        m = MerchantDetails.objects.select_for_update().filter(pk=merchant_id).first()
        if m is None:
            raise NemesisError("REQUEST_NOT_FOUND", "No such version.")
        if m.active or m.approved_by_id is not None:
            raise NemesisError("INVALID_STATE", "This version was already decided.")
        _second_approver(m.created_by_id, staff)
        _activate_merchant(m, staff)
    return m


# ----- flags -----------------------------------------------------------------------------


def set_flag(staff: User, body: dict[str, Any]) -> dict[str, Any]:
    """{field, value}: applied at once, or stored as pending for a second staff member."""
    field, value = body.get("field"), body.get("value")
    if field not in FLAG_FIELDS or not isinstance(value, bool):
        raise NemesisError("INVALID_INPUT", "Choose a flag and a value.", {"field": "Unknown."})
    with transaction.atomic():
        row = services.flags()
        row = type(row).objects.select_for_update().get(pk=row.pk)
        if dual_enabled():
            row.pending_change = {
                "field": field,
                "value": value,
                "proposedBy": staff.pk,
                "proposedAt": timezone.now().isoformat(),
            }
            row.save(update_fields=["pending_change", "updated_at"])
        else:
            setattr(row, FLAG_FIELDS[field], value)
            row.updated_by = staff
            row.save()
    return flags_state(row)


def approve_flag(staff: User) -> dict[str, Any]:
    with transaction.atomic():
        row = services.flags()
        row = type(row).objects.select_for_update().get(pk=row.pk)
        pending = row.pending_change
        if not pending:
            raise NemesisError("INVALID_STATE", "No flag change is waiting.")
        _second_approver(pending.get("proposedBy"), staff)
        setattr(row, FLAG_FIELDS[pending["field"]], pending["value"])
        row.pending_change, row.updated_by = None, staff
        row.save()
    return flags_state(row)


def flags_state(row=None) -> dict[str, Any]:
    row = row or services.flags()
    return {
        "flags": services.flags_payload(row),
        "pending": row.pending_change,
        "updatedAt": row.updated_at,
        "dualApproval": dual_enabled(),
    }


# ----- reconciliation --------------------------------------------------------------------


def record_reconciliation(staff: User, body: dict[str, Any]) -> ReconciliationReport:
    reported = body.get("reportedBalance")
    if not isinstance(reported, int) or isinstance(reported, bool) or reported < 0:
        raise NemesisError(
            "INVALID_INPUT", "Enter the real balance in pesewas.", {"reportedBalance": "Required."}
        )
    owed = ledger.liabilities()
    return ReconciliationReport.objects.create(
        date=date.today(),
        reported_balance=reported,
        ledger_liabilities=owed,
        difference=reported - owed,
        ok=reported >= owed,
        entered_by=staff,
    )


# ----- exclusion -------------------------------------------------------------------------


def remove_permanent_exclusion(user_id: int, staff: User) -> NemesisProfile:
    with transaction.atomic():
        profile = NemesisProfile.objects.select_for_update().filter(user_id=user_id).first()
        if profile is None or not profile.excluded_permanent:
            raise NemesisError("INVALID_STATE", "This account has no permanent break.")
        _not_own(user_id, staff)
        profile.excluded_permanent = False
        profile.save(update_fields=["excluded_permanent"])
    return profile
