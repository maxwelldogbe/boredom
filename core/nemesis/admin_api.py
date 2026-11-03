"""Staff-only Nemesis API under /api/admin/ (same session, CSRF and error format as analytics.api).

Money and ID endpoints need: a staff session that passed two-factor (TWO_FACTOR_REQUIRED), the
specific permission (FORBIDDEN), and for sensitive actions a step-up code from the last
STEP_UP_MINUTES (STEP_UP_REQUIRED). Every response is no-store; every action is written to the
Django admin log. Staff who are not enrolled reach only the 2FA enrolment endpoints here.
"""

import json
from collections.abc import Callable
from datetime import timedelta
from functools import wraps
from typing import Any

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db.models import Case, IntegerField, Model, Sum, Value, When
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_date

from analytics import metrics
from analytics.api import fail, ok
from nemesis import ids, ledger, review, services, staff
from nemesis.errors import NemesisError
from nemesis.models import (
    AdjustmentRequest,
    DepositRequest,
    IdVerification,
    LedgerAccount,
    MerchantDetails,
    ReconciliationReport,
    WithdrawalRequest,
)

View = Callable[..., HttpResponse]
DStatus = DepositRequest.Status
WStatus = WithdrawalRequest.Status
QUEUE_MAX = 200
AUDIT_PAGE = 100
REPORT_STALE_HOURS = 24


def _no_store(response: HttpResponse) -> HttpResponse:
    response["Cache-Control"] = "no-store"
    return response


def _body(request: HttpRequest) -> dict[str, Any]:
    try:
        body = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        raise NemesisError("INVALID_INPUT", "Request body is not valid JSON.") from None
    if not isinstance(body, dict):
        raise NemesisError("INVALID_INPUT", "Request body must be a JSON object.")
    return body


def money_api(
    method: str = "GET",
    *,
    permission: str | None = None,
    step_up: bool = False,
    enrolment: bool = False,
) -> Callable[[View], View]:
    """Staff session, two-factor (unless `enrolment`), permission, step-up, no-store."""

    def decorate(view: View) -> View:
        @wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            user = request.user
            if not user.is_authenticated:
                return _no_store(fail(401, "UNAUTHORIZED", "Log in as staff."))
            if not (user.is_active and user.is_staff):
                return _no_store(fail(403, "FORBIDDEN", "Staff only."))
            if request.method != method:
                return _no_store(fail(405, "METHOD_NOT_ALLOWED", f"Use {method}."))
            try:
                if not enrolment:
                    if not staff.enrolled(user) or not staff.session_verified(request):
                        raise NemesisError(
                            "TWO_FACTOR_REQUIRED", "Set up and use two-factor first."
                        )
                    if permission and not user.has_perm(staff.perm(permission)):
                        raise NemesisError("FORBIDDEN", "You do not have permission for this.")
                    if step_up and not staff.stepped_up(user):
                        raise NemesisError("STEP_UP_REQUIRED", "Enter a code from your app.")
                body = _body(request) if method in ("POST", "PUT") else {}
                response = view(request, body, *args, **kwargs)
            except NemesisError as exc:
                response = JsonResponse(exc.payload(), status=exc.status)
            return _no_store(response)

        return wrapper

    return decorate


def audit(request: HttpRequest, obj: Model, message: str) -> None:
    admin.ModelAdmin(type(obj), admin.site).log_change(request, obj, message)


def _person(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    profile = getattr(user, "profile", None)
    return {
        "userId": user.pk,
        "nickname": profile.nickname if profile else user.username,
        "tag": profile.tag if profile else None,
    }


def _staff_name(user: User | None) -> str | None:
    return user.get_username() if user else None


def _age_seconds(moment) -> int:
    return int((timezone.now() - moment).total_seconds())


# ----- two-factor ------------------------------------------------------------------------


@money_api("POST", enrolment=True)
def twofa_setup(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    return ok(staff.setup(request.user))


@money_api("POST", enrolment=True)
def twofa_confirm(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    codes = staff.confirm(request, request.user, body.get("code"))
    audit(request, staff.security_of(request.user), "Set up two-factor")
    return ok({"backupCodes": codes})


@money_api("POST", enrolment=True)
def twofa_step_up(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    if not staff.enrolled(request.user) or not staff.session_verified(request):
        raise NemesisError("TWO_FACTOR_REQUIRED", "Set up and use two-factor first.")
    staff.step_up(request, request.user, body.get("code"))
    return ok({"ok": True})


# ----- ID review -------------------------------------------------------------------------


def _id_row(v: IdVerification, *, detail: bool = False) -> dict[str, Any]:
    row = {
        "id": v.pk,
        "user": _person(v.user),
        "idType": v.id_type,
        "fullName": v.full_name,
        "last4": v.id_number_last4,
        "status": v.status,
        "attemptNumber": v.attempt_number,
        "flaggedDuplicate": v.flagged_duplicate,
        "createdAt": v.created_at,
        "ageSeconds": _age_seconds(v.created_at),
        "reviewedBy": _staff_name(v.reviewed_by),
        "reviewedAt": v.reviewed_at,
        "rejectionReason": v.rejection_reason or None,
        "hasFront": bool(v.front_path) and v.images_deleted_at is None,
        "hasBack": bool(v.back_path) and v.images_deleted_at is None,
        "imagesDeletedAt": v.images_deleted_at,
    }
    if detail:
        row["submittedDob"] = v.dob
    return row


@money_api(permission="review_ids")
def id_queue(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    status = request.GET.get("status") or IdVerification.Status.PENDING
    rows = IdVerification.objects.select_related("user__profile", "reviewed_by")
    if status != "all":
        rows = rows.filter(status=status)
    rows = rows.order_by("created_at" if status == "pending" else "-created_at")[:QUEUE_MAX]
    return ok({"ids": [_id_row(v) for v in rows]})


def _verification(verification_id: int) -> IdVerification:
    v = (
        IdVerification.objects.select_related("user__profile", "reviewed_by")
        .filter(pk=verification_id)
        .first()
    )
    if v is None:
        raise NemesisError("REQUEST_NOT_FOUND", "No such verification.")
    return v


@money_api(permission="review_ids")
def id_detail(request: HttpRequest, body: dict[str, Any], verification_id: int) -> JsonResponse:
    return ok(_id_row(_verification(verification_id), detail=True))


@money_api(permission="review_ids", step_up=True)
def id_image(
    request: HttpRequest, body: dict[str, Any], verification_id: int, side: str
) -> HttpResponse:
    """Stream one ID photo (private storage, never a public URL). Each view is audit-logged."""
    v = _verification(verification_id)
    if side not in ("front", "back"):
        raise NemesisError("REQUEST_NOT_FOUND", "No such image.")
    path = ids.image_path(v.front_path if side == "front" else v.back_path)
    if path is None or v.images_deleted_at is not None:
        raise NemesisError("REQUEST_NOT_FOUND", "No such image.")
    audit(request, v, f"Viewed {side} ID image")
    content_type = "image/png" if path.suffix == ".png" else "image/jpeg"
    response = FileResponse(open(path, "rb"), content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = "inline"
    return response


@money_api("POST", permission="review_ids", step_up=True)
def id_approve(request: HttpRequest, body: dict[str, Any], verification_id: int) -> JsonResponse:
    raw = body.get("dob")
    dob = parse_date(raw) if isinstance(raw, str) else None
    if dob is None:
        raise NemesisError("INVALID_INPUT", "Re-enter the date of birth.", {"dob": "Required."})
    try:
        v = ids.approve(verification_id, request.user, dob)
    except NemesisError as exc:
        if exc.code == "ID_ALREADY_USED":
            audit(request, _verification(verification_id), "Duplicate ID number flagged")
        raise
    audit(request, v, f"ID {v.status}")
    return ok(_id_row(_verification(v.pk), detail=True))


@money_api("POST", permission="review_ids", step_up=True)
def id_reject(request: HttpRequest, body: dict[str, Any], verification_id: int) -> JsonResponse:
    v = ids.reject(verification_id, request.user, body.get("reason"))
    audit(request, v, f"ID {v.status}: {v.rejection_reason}")
    return ok(_id_row(_verification(v.pk), detail=True))


# ----- deposits --------------------------------------------------------------------------


def _deposit_row(d: DepositRequest, viewer: User) -> dict[str, Any]:
    return {
        "id": d.pk,
        "user": _person(d.user),
        "reference": d.reference,
        "amountRequested": d.amount_requested,
        "amountReceived": d.amount_received,
        "status": d.status,
        "paymentRef": d.payment_ref,
        "senderNumber": d.sender_number,
        "merchantSnapshot": d.merchant_snapshot,
        "createdAt": d.created_at,
        "submittedAt": d.submitted_at,
        "ageSeconds": _age_seconds(d.submitted_at or d.created_at),
        "firstApprovedBy": _staff_name(d.first_approved_by),
        "reviewedBy": _staff_name(d.reviewed_by),
        "reviewedAt": d.reviewed_at,
        "rejectReason": d.reject_reason or None,
        "note": d.note or None,
        "own": d.user_id == viewer.pk,
    }


def _status_queue(model, request: HttpRequest, open_status: str, related: tuple[str, ...]):
    status = request.GET.get("status") or "open"
    rows = model.objects.select_related(*related)
    if status != "all" and status != "open":
        rows = rows.filter(status=status)
    pending_first = Case(
        When(status=open_status, then=Value(0)), default=Value(1), output_field=IntegerField()
    )
    return rows.order_by(pending_first, "-created_at")[:QUEUE_MAX]


@money_api(permission="review_deposits")
def deposit_queue(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    rows = _status_queue(
        DepositRequest,
        request,
        DStatus.PENDING_REVIEW,
        ("user__profile", "first_approved_by", "reviewed_by"),
    )
    return ok(
        {
            "deposits": [_deposit_row(d, request.user) for d in rows],
            "dualApproval": review.dual_enabled(),
        }
    )


def _deposit(deposit_id: int) -> DepositRequest:
    d = (
        DepositRequest.objects.select_related("user__profile", "first_approved_by", "reviewed_by")
        .filter(pk=deposit_id)
        .first()
    )
    if d is None:
        raise NemesisError("REQUEST_NOT_FOUND", "No such deposit.")
    return d


@money_api(permission="review_deposits")
def deposit_detail(request: HttpRequest, body: dict[str, Any], deposit_id: int) -> JsonResponse:
    return ok(_deposit_row(_deposit(deposit_id), request.user))


@money_api("POST", permission="review_deposits", step_up=True)
def deposit_approve(request: HttpRequest, body: dict[str, Any], deposit_id: int) -> JsonResponse:
    d = review.approve_deposit(deposit_id, request.user, body)
    if d.status == DStatus.APPROVED:
        audit(request, d, f"Approved deposit {d.reference}: credited {d.amount_received}")
    else:
        audit(request, d, f"First approval of deposit {d.reference} ({d.amount_received})")
    return ok(_deposit_row(_deposit(d.pk), request.user))


@money_api("POST", permission="review_deposits", step_up=True)
def deposit_reject(request: HttpRequest, body: dict[str, Any], deposit_id: int) -> JsonResponse:
    d = review.reject_deposit(deposit_id, request.user, body)
    audit(request, d, f"Rejected deposit {d.reference}: {d.reject_reason}")
    return ok(_deposit_row(_deposit(d.pk), request.user))


# ----- withdrawals -----------------------------------------------------------------------


def _id_name(user: User | None) -> str | None:
    if user is None:
        return None
    v = IdVerification.objects.filter(user=user, status=IdVerification.Status.APPROVED).first()
    return v.full_name if v else None


def _withdrawal_row(w: WithdrawalRequest, viewer: User) -> dict[str, Any]:
    return {
        "id": w.pk,
        "user": _person(w.user),
        "idName": _id_name(w.user),
        "amount": w.amount,
        "status": w.status,
        "payoutSnapshot": w.payout_snapshot,
        "createdAt": w.created_at,
        "eligibleAt": w.eligible_at,
        "eligible": w.eligible_at <= timezone.now(),
        "ageSeconds": _age_seconds(w.created_at),
        "firstApprovedBy": _staff_name(w.first_approved_by),
        "reviewedBy": _staff_name(w.reviewed_by),
        "reviewedAt": w.reviewed_at,
        "payoutReference": w.payout_reference or None,
        "paidBy": _staff_name(w.paid_by),
        "paidAt": w.paid_at,
        "rejectReason": w.reject_reason or None,
        "own": w.user_id == viewer.pk,
    }


WITHDRAWAL_RELATED = ("user__profile", "first_approved_by", "reviewed_by", "paid_by")


@money_api(permission="review_withdrawals")
def withdrawal_queue(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    rows = _status_queue(WithdrawalRequest, request, WStatus.PENDING_REVIEW, WITHDRAWAL_RELATED)
    return ok(
        {
            "withdrawals": [_withdrawal_row(w, request.user) for w in rows],
            "dualApproval": review.dual_enabled(),
        }
    )


def _withdrawal(withdrawal_id: int) -> WithdrawalRequest:
    w = (
        WithdrawalRequest.objects.select_related(*WITHDRAWAL_RELATED)
        .filter(pk=withdrawal_id)
        .first()
    )
    if w is None:
        raise NemesisError("REQUEST_NOT_FOUND", "No such withdrawal.")
    return w


def _withdrawal_response(request: HttpRequest, withdrawal_id: int) -> JsonResponse:
    return ok(_withdrawal_row(_withdrawal(withdrawal_id), request.user))


@money_api(permission="review_withdrawals")
def withdrawal_detail(
    request: HttpRequest, body: dict[str, Any], withdrawal_id: int
) -> JsonResponse:
    return _withdrawal_response(request, withdrawal_id)


@money_api("POST", permission="review_withdrawals", step_up=True)
def withdrawal_approve(
    request: HttpRequest, body: dict[str, Any], withdrawal_id: int
) -> JsonResponse:
    w = review.approve_withdrawal(withdrawal_id, request.user)
    verb = "Approved" if w.status == WStatus.APPROVED else "First approval of"
    audit(request, w, f"{verb} withdrawal {w.pk} ({w.amount})")
    return _withdrawal_response(request, w.pk)


@money_api("POST", permission="review_withdrawals", step_up=True)
def withdrawal_mark_paid(
    request: HttpRequest, body: dict[str, Any], withdrawal_id: int
) -> JsonResponse:
    w = review.mark_paid(withdrawal_id, request.user, body)
    audit(request, w, f"Marked withdrawal {w.pk} paid ({w.amount}), ref {w.payout_reference}")
    return _withdrawal_response(request, w.pk)


@money_api("POST", permission="review_withdrawals", step_up=True)
def withdrawal_reject(
    request: HttpRequest, body: dict[str, Any], withdrawal_id: int
) -> JsonResponse:
    w = review.reject_withdrawal(withdrawal_id, request.user, body)
    audit(request, w, f"Rejected withdrawal {w.pk}: {w.reject_reason}")
    return _withdrawal_response(request, w.pk)


# ----- adjustments -----------------------------------------------------------------------


def _adjustment_row(a: AdjustmentRequest) -> dict[str, Any]:
    return {
        "id": a.pk,
        "user": _person(a.user),
        "amount": a.amount,
        "reason": a.reason,
        "status": a.status,
        "proposedBy": _staff_name(a.proposed_by),
        "approvedBy": _staff_name(a.approved_by),
        "createdAt": a.created_at,
        "decidedAt": a.decided_at,
    }


ADJUSTMENT_RELATED = ("user__profile", "proposed_by", "approved_by")


@money_api(permission="adjust_balances")
def adjustments(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    rows = AdjustmentRequest.objects.select_related(*ADJUSTMENT_RELATED).order_by("-created_at")
    return ok(
        {
            "adjustments": [_adjustment_row(a) for a in rows[:QUEUE_MAX]],
            "dualApproval": review.dual_enabled(),
        }
    )


def _adjustment_response(adjustment_id: int) -> JsonResponse:
    a = AdjustmentRequest.objects.select_related(*ADJUSTMENT_RELATED).get(pk=adjustment_id)
    return ok(_adjustment_row(a))


@money_api("POST", permission="adjust_balances", step_up=True)
def adjustment_propose(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    a = review.propose_adjustment(request.user, body)
    audit(request, a, f"Adjustment {a.amount:+d} {a.status}: {a.reason}")
    return _adjustment_response(a.pk)


@money_api("POST", permission="adjust_balances", step_up=True)
def adjustment_decide(
    request: HttpRequest, body: dict[str, Any], adjustment_id: int, action: str
) -> JsonResponse:
    if action == "approve":
        a = review.approve_adjustment(adjustment_id, request.user)
    elif action == "reject":
        a = review.reject_adjustment(adjustment_id, request.user)
    else:
        raise NemesisError("REQUEST_NOT_FOUND", "Unknown action.")
    audit(request, a, f"Adjustment {a.amount:+d} {a.status}")
    return _adjustment_response(a.pk)


# ----- merchant details and flags --------------------------------------------------------


def _merchant_row(m: MerchantDetails) -> dict[str, Any]:
    return {
        "id": m.pk,
        "method": m.method,
        "network": m.network,
        "number": m.number,
        "accountName": m.account_name,
        "active": m.active,
        "pending": not m.active and m.approved_by_id is None,
        "createdBy": _staff_name(m.created_by),
        "approvedBy": _staff_name(m.approved_by),
        "createdAt": m.created_at,
        "activatedAt": m.activated_at,
    }


def _merchant_state() -> dict[str, Any]:
    rows = MerchantDetails.objects.select_related("created_by", "approved_by").order_by(
        "-created_at"
    )
    versions = [_merchant_row(m) for m in rows[:50]]
    return {
        "active": next((v for v in versions if v["active"]), None),
        "versions": versions,
        "dualApproval": review.dual_enabled(),
    }


@money_api()
def merchant(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    return ok(_merchant_state())


@money_api("PUT", permission="edit_merchant", step_up=True)
def merchant_propose(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    m = review.propose_merchant(request.user, body)
    state = "now active" if m.active else "waiting for a second approval"
    audit(request, m, f"New merchant details {m.network} {m.number} ({state})")
    return ok(_merchant_state())


@money_api("POST", permission="edit_merchant", step_up=True)
def merchant_approve(request: HttpRequest, body: dict[str, Any], merchant_id: int) -> JsonResponse:
    m = review.approve_merchant(merchant_id, request.user)
    audit(request, m, f"Approved merchant details {m.network} {m.number}")
    return ok(_merchant_state())


def merchant_dispatch(request: HttpRequest) -> HttpResponse:
    return (merchant_propose if request.method == "PUT" else merchant)(request)


@money_api()
def flags(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    return ok(review.flags_state())


@money_api("POST", permission="edit_flags", step_up=True)
def flag_set(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    state = review.set_flag(request.user, body)
    verb = "Proposed" if state["pending"] else "Set"
    audit(request, services.flags(), f"{verb} {body.get('field')} = {body.get('value')}")
    return ok(state)


@money_api("POST", permission="edit_flags", step_up=True)
def flag_approve(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    state = review.approve_flag(request.user)
    audit(request, services.flags(), "Approved the pending flag change")
    return ok(state)


def flags_dispatch(request: HttpRequest) -> HttpResponse:
    return (flag_set if request.method == "POST" else flags)(request)


# ----- reconciliation and overview -------------------------------------------------------


def _report_row(r: ReconciliationReport | None) -> dict[str, Any] | None:
    if r is None:
        return None
    return {
        "id": r.pk,
        "date": r.date,
        "reportedBalance": r.reported_balance,
        "ledgerLiabilities": r.ledger_liabilities,
        "difference": r.difference,
        "ok": r.ok,
        "enteredBy": _staff_name(r.entered_by),
        "createdAt": r.created_at,
    }


def _reconcile_state() -> dict[str, Any]:
    rows = ReconciliationReport.objects.select_related("entered_by").order_by("-created_at")
    reports = [_report_row(r) for r in rows[:50]]
    return {
        "latest": reports[0] if reports else None,
        "history": reports,
        "ledger": ledger.reconcile().as_dict(),
    }


@money_api("GET", permission="review_deposits")
def reconcile(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    return ok(_reconcile_state())


@money_api("POST", permission="review_deposits")
def reconcile_record(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    r = review.record_reconciliation(request.user, body)
    audit(request, r, f"Reconciliation: reported {r.reported_balance}, owed {r.ledger_liabilities}")
    return ok(_reconcile_state())


def reconcile_dispatch(request: HttpRequest) -> HttpResponse:
    return (reconcile_record if request.method == "POST" else reconcile)(request)


def pending_counts() -> dict[str, int]:
    return {
        "deposits": DepositRequest.objects.filter(status=DStatus.PENDING_REVIEW).count(),
        "withdrawals": WithdrawalRequest.objects.filter(
            status__in=[WStatus.PENDING_REVIEW, WStatus.APPROVED]
        ).count(),
        "ids": IdVerification.objects.filter(status=IdVerification.Status.PENDING).count(),
        "adjustments": AdjustmentRequest.objects.filter(
            status=AdjustmentRequest.Status.PENDING
        ).count(),
    }


@money_api()
def overview(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    rng = metrics.parse_range(request.GET.get("range"))
    approved = DepositRequest.objects.filter(status=DStatus.APPROVED)
    paid = WithdrawalRequest.objects.filter(status=WStatus.PAID)
    if rng.since is not None:
        approved = approved.filter(reviewed_at__gte=rng.since)
        paid = paid.filter(paid_at__gte=rng.since)
    deposits_total = approved.aggregate(s=Sum("amount_received"))["s"]
    withdrawals_total = paid.aggregate(s=Sum("amount"))["s"]
    check = ledger.reconcile()
    latest = ReconciliationReport.objects.order_by("-created_at").first()
    warnings = []
    if latest is None or latest.created_at < timezone.now() - timedelta(hours=REPORT_STALE_HOURS):
        warnings.append("report_stale")
    if latest is not None and not latest.ok:
        warnings.append("report_short")
    if not check.ok:
        warnings.append("ledger_mismatch")
    last_merchant = MerchantDetails.objects.order_by("-created_at").first()
    return ok(
        {
            "range": {"key": rng.key, "label": rng.label},
            "ranges": [{"key": k, "label": v} for k, v in metrics.RANGES.items()],
            "liabilities": check.liabilities,
            "depositsTotal": deposits_total or 0,
            "withdrawalsTotal": withdrawals_total or 0,
            "pending": pending_counts(),
            "latestReport": _report_row(latest),
            "ledgerOk": check.ok,
            "warnings": warnings,
            "lastMerchantChange": last_merchant.created_at if last_merchant else None,
            "flags": services.flags_payload(),
            "dualApproval": review.dual_enabled(),
        }
    )


# ----- users and audit -------------------------------------------------------------------


@money_api()
def user_money(request: HttpRequest, body: dict[str, Any], user_id: int) -> JsonResponse:
    """Verification (review_ids) and wallet (any money permission) for one account."""
    target = User.objects.filter(pk=user_id).first()
    if target is None:
        raise NemesisError("REQUEST_NOT_FOUND", "No such account.")
    perms = staff.permissions_of(request.user)
    profile = services.profile_of(target)
    now = timezone.now()
    money_perms = {"review_deposits", "review_withdrawals", "adjust_balances"}
    return ok(
        {
            "verification": ids.id_state(target) if "review_ids" in perms else None,
            "wallet": (
                {
                    "balance": ledger.balance(LedgerAccount.Kind.USER, target),
                    "held": ledger.balance(LedgerAccount.Kind.WITHDRAWAL_HOLD, target),
                    "active": bool(profile and profile.active),
                    "exclusion": services.exclusion_payload(profile, now),
                }
                if money_perms & set(perms)
                else None
            ),
            "canRemoveExclusion": "adjust_balances" in perms,
        }
    )


@money_api("POST", permission="adjust_balances", step_up=True)
def remove_exclusion(request: HttpRequest, body: dict[str, Any], user_id: int) -> JsonResponse:
    profile = review.remove_permanent_exclusion(user_id, request.user)
    audit(request, profile, "Removed permanent Nemesis break")
    return ok({"ok": True})


@money_api()
def money_audit(request: HttpRequest, body: dict[str, Any]) -> JsonResponse:
    """Admin log rows about Nemesis records (and Nemesis actions on accounts)."""
    types = ContentType.objects.filter(app_label="nemesis")
    rows = (
        LogEntry.objects.filter(content_type__in=types)
        .select_related("user", "content_type")
        .order_by("-action_time")[:AUDIT_PAGE]
    )
    return ok(
        {
            "entries": [
                {
                    "id": e.pk,
                    "at": e.action_time,
                    "staff": e.user.get_username(),
                    "model": e.content_type.model if e.content_type else None,
                    "objectId": e.object_id,
                    "object": e.object_repr,
                    "message": e.get_change_message(),
                }
                for e in rows
            ]
        }
    )
