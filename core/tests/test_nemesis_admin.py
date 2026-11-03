"""Nemesis staff tools: TOTP 2FA, step-up, permissions, money review, dual approval, deletion."""

import threading
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Group, Permission, User
from django.db import close_old_connections, connection
from django.test import Client
from django.utils import timezone

from analytics.lockout import admin_lockout
from games.constants import ADMIN_LOGIN_MAX_FAILS, DUAL_APPROVAL_THRESHOLD
from nemesis import ids, ledger, review, staff, totp
from nemesis.errors import NemesisError
from nemesis.models import (
    DepositRequest,
    IdVerification,
    LedgerAccount,
    LedgerEntry,
    MerchantDetails,
    NemesisProfile,
    StaffSecurity,
    WithdrawalRequest,
)
from tests.nemesis_helpers import PNG, account_user, auth

pytestmark = pytest.mark.django_db
Kind = LedgerAccount.Kind
PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def setup(settings, tmp_path: Path) -> None:
    settings.NEMESIS_ENABLED = True
    settings.DUAL_APPROVAL_ENABLED = False
    settings.PRIVATE_UPLOAD_DIR = tmp_path
    admin_lockout.reset()


def code_for(user: User, offset: int = 0) -> str:
    sec = StaffSecurity.objects.get(user=user)
    return totp.code_at(sec.totp_secret, totp.current_step() + offset)


def make_staff(*perms: str, enrolled: bool = True) -> User:
    user = account_user(staff=True)
    group = Group.objects.create(name=f"money-{user.pk}")
    group.permissions.set(Permission.objects.filter(codename__in=perms))
    user.groups.add(group)
    if enrolled:
        StaffSecurity.objects.create(
            user=user, totp_secret=totp.new_secret(), enrolled_at=timezone.now()
        )
    return User.objects.get(pk=user.pk)  # fresh permission cache


def staff_client(user: User, *, step_up: bool = True) -> Client:
    client = Client()
    client.force_login(user)
    session = client.session
    session[staff.SESSION_KEY] = user.pk
    session.save()
    if step_up:
        StaffSecurity.objects.filter(user=user).update(last_step_up_at=timezone.now())
    return client


def post(client: Client, path: str, body=None):
    return client.post(path, body or {}, content_type="application/json")


def funded(amount: int) -> User:
    user = account_user()
    NemesisProfile.objects.create(user=user, active=True)
    ledger.post_transaction(
        "deposit",
        f"seed:{user.pk}",
        [(ledger.account(Kind.EXTERNAL), -amount), (ledger.account(Kind.USER, user), amount)],
    )
    return user


def pending_deposit(user: User | None = None, amount: int = 5000) -> DepositRequest:
    user = user or account_user()
    return DepositRequest.objects.create(
        user=user,
        reference=f"NEM-{user.pk:06d}"[:10],
        amount_requested=amount,
        status="pending_review",
        payment_ref=f"TX{user.pk}",
        sender_number="0241112222",
        expires_at=timezone.now(),
        submitted_at=timezone.now(),
    )


def withdrawal(user: User, amount: int, *, eligible: bool = True) -> WithdrawalRequest:
    w = WithdrawalRequest.objects.create(
        user=user,
        amount=amount,
        eligible_at=timezone.now() - timedelta(minutes=1 if eligible else -60),
        payout_snapshot={"network": "MTN MoMo", "number": "0245551234", "accountName": "Ama"},
    )
    ledger.post_transaction(
        "withdrawal_hold",
        f"withdrawal:{w.pk}:hold",
        [
            (ledger.account(Kind.USER, user), -amount),
            (ledger.account(Kind.WITHDRAWAL_HOLD, user), amount),
        ],
    )
    return w


# ----- TOTP and login --------------------------------------------------------------------


def test_totp_matches_rfc6238_vector() -> None:
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # "12345678901234567890"
    assert totp.code_at(secret, 59 // 30) == "287082"
    assert totp.match_step(secret, "287082", now=59) == 1
    assert totp.match_step(secret, "287082", now=59 + 90) is None


def test_enrolment_backup_codes_and_login_code() -> None:
    user = make_staff(enrolled=False)
    client = Client()
    client.force_login(user)
    assert client.get("/api/admin/money/overview").json()["error"]["code"] == "TWO_FACTOR_REQUIRED"
    setup_body = post(client, "/api/admin/2fa/setup").json()
    assert setup_body["otpauthUri"].startswith("otpauth://totp/")
    assert post(client, "/api/admin/2fa/confirm", {"code": "000000"}).status_code == 400
    codes = post(client, "/api/admin/2fa/confirm", {"code": code_for(user)}).json()["backupCodes"]
    assert len(codes) == 10
    assert totp.hash_backup(codes[0]) in StaffSecurity.objects.get(user=user).backup_codes_hash
    assert codes[0] not in str(StaffSecurity.objects.get(user=user).backup_codes_hash)

    login = Client()
    creds = {"username": user.username, "password": PASSWORD}
    assert post(login, "/api/admin/login", creds).json()["error"]["code"] == "CODE_REQUIRED"
    assert post(login, "/api/admin/login", {**creds, "code": codes[1]}).status_code == 200
    assert login.get("/api/admin/money/overview").status_code == 200
    again = post(Client(), "/api/admin/login", {**creds, "code": codes[1]})
    assert again.json()["error"]["code"] == "INVALID_CODE"  # backup codes are single use


def test_code_replay_is_rejected() -> None:
    user = make_staff()
    code = code_for(user)
    assert staff.check_code(user, code, allow_backup=False)
    assert not staff.check_code(user, code, allow_backup=False)


def test_wrong_codes_lock_out() -> None:
    user = make_staff()
    client = staff_client(user, step_up=False)
    for _ in range(ADMIN_LOGIN_MAX_FAILS):
        assert post(client, "/api/admin/2fa/step-up", {"code": "000000"}).status_code == 400
    locked = post(client, "/api/admin/2fa/step-up", {"code": code_for(user)})
    assert locked.json()["error"]["code"] == "LOCKED"


def test_password_only_session_cannot_reach_money() -> None:
    user = make_staff("review_deposits")
    client = Client()
    client.force_login(user)  # e.g. the Django admin login, no code
    assert client.get("/api/admin/money/deposits").json()["error"]["code"] == "TWO_FACTOR_REQUIRED"


# ----- step-up and permissions -----------------------------------------------------------

SENSITIVE = [
    ("review_ids", "/api/admin/ids/1/approve"),
    ("review_ids", "/api/admin/ids/1/reject"),
    ("review_deposits", "/api/admin/money/deposits/1/approve"),
    ("review_deposits", "/api/admin/money/deposits/1/reject"),
    ("review_withdrawals", "/api/admin/money/withdrawals/1/approve"),
    ("review_withdrawals", "/api/admin/money/withdrawals/1/mark-paid"),
    ("review_withdrawals", "/api/admin/money/withdrawals/1/reject"),
    ("adjust_balances", "/api/admin/money/adjustments/propose"),
    ("edit_flags", "/api/admin/money/flags"),
]


@pytest.mark.parametrize(("perm", "path"), SENSITIVE)
def test_sensitive_actions_need_permission_then_step_up(perm: str, path: str) -> None:
    outsider = staff_client(make_staff())
    assert post(outsider, path).json()["error"]["code"] == "FORBIDDEN"
    member = make_staff(perm)
    client = staff_client(member, step_up=False)
    assert post(client, path).json()["error"]["code"] == "STEP_UP_REQUIRED"
    assert post(client, "/api/admin/2fa/step-up", {"code": code_for(member)}).status_code == 200
    assert post(client, path).json()["error"]["code"] != "STEP_UP_REQUIRED"


def test_merchant_change_needs_step_up() -> None:
    member = make_staff("edit_merchant")
    client = staff_client(member, step_up=False)
    res = client.put("/api/admin/money/merchant", {}, content_type="application/json")
    assert res.json()["error"]["code"] == "STEP_UP_REQUIRED"


def test_expired_step_up() -> None:
    member = make_staff("review_deposits")
    client = staff_client(member)
    StaffSecurity.objects.filter(user=member).update(
        last_step_up_at=timezone.now() - timedelta(minutes=30)
    )
    res = post(client, f"/api/admin/money/deposits/{pending_deposit().pk}/reject", {"reason": "x"})
    assert res.json()["error"]["code"] == "STEP_UP_REQUIRED"


# ----- ID images -------------------------------------------------------------------------


def test_id_images_need_staff_step_up_and_are_audited(client: Client) -> None:
    player = account_user()
    v = IdVerification.objects.create(
        user=player,
        id_type="passport",
        full_name="Ama Mensah",
        id_number_hash="h",
        dob="1990-01-01",
        front_path=ids.save_image(PNG),
        attempt_number=1,
    )
    path = f"/api/admin/ids/{v.pk}/image/front"
    assert client.get(path, **auth(player)).status_code == 401  # a player token is not staff
    reviewer = make_staff("review_ids")
    no_step = staff_client(reviewer, step_up=False)
    assert no_step.get(path).json()["error"]["code"] == "STEP_UP_REQUIRED"
    ok = staff_client(reviewer)
    res = ok.get(path)
    assert res.status_code == 200 and b"".join(res.streaming_content) == PNG
    assert res["Cache-Control"] == "no-store"
    assert LogEntry.objects.filter(object_id=str(v.pk), change_message__contains="Viewed").exists()
    approved = post(ok, f"/api/admin/ids/{v.pk}/approve", {"dob": "1990-01-01"}).json()
    assert approved["status"] == "approved"


# ----- deposits --------------------------------------------------------------------------


def test_deposit_approval_with_different_amount_and_twice() -> None:
    reviewer = staff_client(make_staff("review_deposits"))
    d = pending_deposit(amount=5000)
    path = f"/api/admin/money/deposits/{d.pk}/approve"
    unchecked = post(reviewer, path, {"receivedAmount": 5000})
    assert "verifiedInAccount" in unchecked.json()["error"]["fields"]
    no_note = post(reviewer, path, {"receivedAmount": 4000, "verifiedInAccount": True})
    assert "note" in no_note.json()["error"]["fields"]
    body = {"receivedAmount": 4000, "verifiedInAccount": True, "note": "Short payment"}
    assert post(reviewer, path, body).json()["status"] == "approved"
    assert ledger.balance(Kind.USER, d.user) == 4000
    assert post(reviewer, path, body).json()["error"]["code"] == "INVALID_STATE"
    assert ledger.balance(Kind.USER, d.user) == 4000


def test_staff_cannot_approve_their_own_deposit() -> None:
    member = make_staff("review_deposits")
    d = pending_deposit(member)
    res = post(
        staff_client(member),
        f"/api/admin/money/deposits/{d.pk}/approve",
        {"receivedAmount": 5000, "verifiedInAccount": True},
    )
    assert res.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.django_db(transaction=True)
def test_concurrent_deposit_approvals_credit_once() -> None:
    if connection.vendor != "postgresql":
        pytest.skip(
            "Concurrency test needs PostgreSQL (set DATABASE_URL); SQLite has no row locks."
        )
    reviewer = make_staff("review_deposits")
    d = pending_deposit()
    results = []

    def approve() -> None:
        try:
            review.approve_deposit(
                d.pk, reviewer, {"receivedAmount": 5000, "verifiedInAccount": True}
            )
            results.append("ok")
        except NemesisError as exc:
            results.append(exc.code)
        finally:
            close_old_connections()

    threads = [threading.Thread(target=approve) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 1
    assert ledger.balance(Kind.USER, d.user) == 5000


# ----- withdrawals -----------------------------------------------------------------------


def test_withdrawal_approve_mark_paid_and_reject_refund() -> None:
    reviewer = staff_client(make_staff("review_withdrawals"))
    user = funded(10000)
    early = withdrawal(user, 3000, eligible=False)
    res = post(reviewer, f"/api/admin/money/withdrawals/{early.pk}/approve")
    assert res.json()["error"]["code"] == "INVALID_STATE"
    rejected = post(reviewer, f"/api/admin/money/withdrawals/{early.pk}/reject", {"reason": "No"})
    assert rejected.json()["status"] == "rejected"
    assert ledger.balance(Kind.USER, user) == 10000

    w = withdrawal(user, 4000)
    assert post(reviewer, f"/api/admin/money/withdrawals/{w.pk}/approve").json()["status"] == (
        "approved"
    )
    paid = post(
        reviewer, f"/api/admin/money/withdrawals/{w.pk}/mark-paid", {"payoutReference": "MP123"}
    ).json()
    assert paid["status"] == "paid" and paid["payoutReference"] == "MP123"
    assert ledger.balance(Kind.WITHDRAWAL_HOLD, user) == 0
    assert ledger.balance(Kind.USER, user) == 6000
    assert ledger.liabilities() == 6000 and ledger.reconcile().ok


# ----- dual approval, adjustments, merchant, flags ---------------------------------------


def test_dual_approval_needs_a_second_different_staff(settings) -> None:
    settings.DUAL_APPROVAL_ENABLED = True
    first_staff = make_staff("review_deposits")
    second_staff = make_staff("review_deposits")
    d = pending_deposit(amount=DUAL_APPROVAL_THRESHOLD)
    body = {"receivedAmount": DUAL_APPROVAL_THRESHOLD, "verifiedInAccount": True}
    path = f"/api/admin/money/deposits/{d.pk}/approve"
    first = staff_client(first_staff)
    assert post(first, path, body).json()["status"] == "pending_review"
    assert post(first, path, body).json()["error"]["code"] == "FORBIDDEN"
    assert ledger.balance(Kind.USER, d.user) == 0
    assert post(staff_client(second_staff), path, body).json()["status"] == "approved"
    assert ledger.balance(Kind.USER, d.user) == DUAL_APPROVAL_THRESHOLD


def test_adjustments_dual_off_and_on(settings) -> None:
    player = funded(1000)
    adjuster = staff_client(make_staff("adjust_balances"))
    body = {"userId": player.pk, "amount": -500, "reason": "Duplicate credit"}
    applied = post(adjuster, "/api/admin/money/adjustments/propose", body).json()
    assert applied["status"] == "applied"
    assert ledger.balance(Kind.USER, player) == 500
    touched = LedgerEntry.objects.filter(transaction__kind="adjustment").values_list(
        "account__kind", flat=True
    )
    assert set(touched) == {"user", "external"}  # never escrow
    settings.DUAL_APPROVAL_ENABLED = True
    pending = post(adjuster, "/api/admin/money/adjustments/propose", {**body, "amount": 200}).json()
    assert pending["status"] == "pending"
    own = post(adjuster, f"/api/admin/money/adjustments/{pending['id']}/approve")
    assert own.json()["error"]["code"] == "FORBIDDEN"
    other = staff_client(make_staff("adjust_balances"))
    assert (
        post(other, f"/api/admin/money/adjustments/{pending['id']}/approve").json()["status"]
        == "applied"
    )
    assert ledger.balance(Kind.USER, player) == 700


def test_merchant_change_keeps_open_snapshots() -> None:
    editor = staff_client(make_staff("edit_merchant"))
    body = {
        "method": "mobile_money",
        "network": "MTN MoMo",
        "number": "0240000001",
        "accountName": "Boredom Ltd",
    }
    editor.put("/api/admin/money/merchant", body, content_type="application/json")
    first = MerchantDetails.objects.get(active=True)
    player = account_user()
    open_dep = DepositRequest.objects.create(
        user=player,
        reference="NEM-OPEN01",
        amount_requested=5000,
        merchant_snapshot={"number": first.number},
        expires_at=timezone.now() + timedelta(hours=1),
    )
    state = editor.put(
        "/api/admin/money/merchant",
        {**body, "number": "0559999999"},
        content_type="application/json",
    ).json()
    assert state["active"]["number"] == "0559999999" and len(state["versions"]) == 2
    open_dep.refresh_from_db()
    assert open_dep.merchant_snapshot["number"] == "0240000001"


def test_flags_switch_deposits_off(client: Client) -> None:
    editor = staff_client(make_staff("edit_flags"))
    state = post(
        editor, "/api/admin/money/flags", {"field": "depositsEnabled", "value": False}
    ).json()
    assert state["flags"]["depositsEnabled"] is False
    player = account_user()
    NemesisProfile.objects.create(user=player, active=True)
    res = client.post(
        "/api/wallet/deposits", {"amount": 5000}, content_type="application/json", **auth(player)
    )
    assert res.json()["error"]["code"] == "FEATURE_DISABLED"


def test_reconciliation_and_overview_warning() -> None:
    funded(7000)
    member = staff_client(make_staff("review_deposits"))
    overview = member.get("/api/admin/money/overview").json()
    assert overview["liabilities"] == 7000 and "report_stale" in overview["warnings"]
    state = post(member, "/api/admin/money/reconcile", {"reportedBalance": 6000}).json()
    assert state["latest"]["ok"] is False and state["latest"]["difference"] == -1000
    assert "report_short" in member.get("/api/admin/money/overview").json()["warnings"]


# ----- deletion --------------------------------------------------------------------------


def test_deletion_blocked_with_funds(client: Client) -> None:
    player = funded(1000)
    res = client.delete(
        "/api/auth/account", {"password": PASSWORD}, content_type="application/json", **auth(player)
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "HAS_FUNDS"
    superuser = account_user(staff=True)
    User.objects.filter(pk=superuser.pk).update(is_superuser=True)
    admin_client = Client()
    admin_client.force_login(User.objects.get(pk=superuser.pk))
    blocked = post(admin_client, f"/api/admin/users/u/{player.pk}/delete")
    assert blocked.json()["error"]["code"] == "HAS_FUNDS"
    assert User.objects.filter(pk=player.pk).exists()
