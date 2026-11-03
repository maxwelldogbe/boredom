"""Nemesis deposits, payout destination, withdrawals, limits and self-exclusion (player side)."""

import itertools
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from games.constants import (
    DEPOSIT_DAILY_LIMIT,
    DEPOSIT_MIN,
    LIMIT_RAISE_DELAY_HOURS,
    PAYOUT_CHANGE_DELAY_HOURS,
    WITHDRAW_DAILY_CAP,
    WITHDRAW_FIRST_DELAY_HOURS,
    WITHDRAW_MIN,
)
from nemesis import ledger, tasks, views
from nemesis.models import (
    DepositRequest,
    LedgerAccount,
    MerchantDetails,
    NemesisProfile,
    WithdrawalRequest,
)
from tests.nemesis_helpers import account_user, auth

pytestmark = pytest.mark.django_db
Kind = LedgerAccount.Kind
PASSWORD = "correct horse battery"
_keys = itertools.count(1)


@pytest.fixture(autouse=True)
def nemesis_on(settings) -> None:
    settings.NEMESIS_ENABLED = True
    cache.clear()
    views.password_limiter.reset()
    MerchantDetails.objects.create(
        method="mobile_money",
        network="MTN MoMo",
        number="0240000001",
        account_name="Boredom Ltd",
        active=True,
    )


def player(*, active: bool = True, funds: int = 0):
    user = account_user()
    NemesisProfile.objects.create(user=user, active=active)
    if funds:
        ledger.post_transaction(
            "deposit",
            f"seed:{next(_keys)}",
            [(ledger.account(Kind.EXTERNAL), -funds), (ledger.account(Kind.USER, user), funds)],
        )
    return user


def post(client: Client, user, path: str, body=None, key: str | None = None):
    headers = auth(user)
    if key:
        headers["HTTP_IDEMPOTENCY_KEY"] = key
    return client.post(path, body or {}, content_type="application/json", **headers)


def put(client: Client, user, path: str, body):
    return client.put(path, body, content_type="application/json", **auth(user))


# ----- deposits --------------------------------------------------------------------------


def test_deposit_flow_and_one_open_request(client) -> None:
    user = player()
    res = post(client, user, "/api/wallet/deposits", {"amount": 5000})
    assert res.status_code == 201
    dep = res.json()
    assert dep["reference"].startswith("NEM-") and len(dep["reference"]) == 10
    assert dep["paymentDetails"]["number"] == "0240000001"
    again = post(client, user, "/api/wallet/deposits", {"amount": 5000}).json()["error"]
    assert again["code"] == "DEPOSIT_OPEN"
    body = {"paymentRef": "ab-12 34.56", "senderNumber": "+233 24 111 2222"}
    first = post(client, user, f"/api/wallet/deposits/{dep['id']}/submit", body).json()
    assert first["status"] == "pending_review" and first["paymentRef"] == "AB123456"
    retry = post(client, user, f"/api/wallet/deposits/{dep['id']}/submit", body).json()
    assert retry == first
    assert client.get("/api/wallet/deposits", **auth(user)).json()["open"]["id"] == dep["id"]


def test_deposit_needs_active_and_not_excluded(client) -> None:
    off = player(active=False)
    assert (
        post(client, off, "/api/wallet/deposits", {"amount": 5000}).json()["error"]["code"]
        == "NOT_ACTIVE"
    )
    user = player()
    NemesisProfile.objects.filter(user=user).update(excluded_permanent=True)
    assert (
        post(client, user, "/api/wallet/deposits", {"amount": 5000}).json()["error"]["code"]
        == "EXCLUDED"
    )


def test_deposit_limits(client) -> None:
    user = player()
    NemesisProfile.objects.filter(user=user).update(deposit_daily_limit=6000)
    DepositRequest.objects.create(
        user=user,
        reference="NEM-AAAAAA",
        amount_requested=5000,
        amount_received=4000,
        status="approved",
        expires_at=timezone.now(),
    )
    err = post(client, user, "/api/wallet/deposits", {"amount": 3000}).json()["error"]
    assert err["code"] == "LIMIT_REACHED" and err["remaining"] == 2000
    assert post(client, user, "/api/wallet/deposits", {"amount": 2000}).status_code == 201


def test_payment_ref_is_unique_among_active_requests(client) -> None:
    a, b = player(), player()
    body = {"paymentRef": "TX999", "senderNumber": "0241112222"}
    da = post(client, a, "/api/wallet/deposits", {"amount": 5000}).json()
    db = post(client, b, "/api/wallet/deposits", {"amount": 5000}).json()
    post(client, a, f"/api/wallet/deposits/{da['id']}/submit", body)
    err = post(client, b, f"/api/wallet/deposits/{db['id']}/submit", body).json()["error"]
    assert err["code"] == "DUPLICATE_REFERENCE"


def test_unpaid_deposit_expires_and_cancel(client) -> None:
    user = player()
    dep = post(client, user, "/api/wallet/deposits", {"amount": 5000}).json()
    DepositRequest.objects.filter(pk=dep["id"]).update(expires_at=timezone.now())
    tasks.frequent()
    assert DepositRequest.objects.get(pk=dep["id"]).status == "expired"
    second = post(client, user, "/api/wallet/deposits", {"amount": 5000}).json()
    cancelled = post(client, user, f"/api/wallet/deposits/{second['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"


def test_idempotency_key_replays_the_first_response(client) -> None:
    user = player()
    first = post(client, user, "/api/wallet/deposits", {"amount": 5000}, key="k-1")
    again = post(client, user, "/api/wallet/deposits", {"amount": 5000}, key="k-1")
    assert again.status_code == 201 and again.json() == first.json()
    assert DepositRequest.objects.filter(user=user).count() == 1


# ----- payout and withdrawals ------------------------------------------------------------

DEST = {
    "method": "mobile_money",
    "network": "MTN MoMo",
    "number": "024 555 1234",
    "accountName": "Ama Mensah",
    "password": PASSWORD,
}


def test_payout_needs_password_and_is_masked(client) -> None:
    user = player()
    wrong = post(client, user, "/api/wallet/payout-destination", {**DEST, "password": "nope"})
    assert wrong.json()["error"]["fields"]["password"]
    payout = post(client, user, "/api/wallet/payout-destination", DEST).json()["payout"]
    assert payout["number"].endswith("234") and "0245551234" not in payout["number"]
    assert payout["effective"] is True


def test_withdrawal_holds_funds_with_first_delay_and_cancel(client) -> None:
    user = player(funds=10000)
    post(client, user, "/api/wallet/payout-destination", DEST)
    res = post(client, user, "/api/wallet/withdrawals", {"amount": 4000})
    assert res.status_code == 201
    w = res.json()
    assert ledger.balance(Kind.USER, user) == 6000
    assert ledger.balance(Kind.WITHDRAWAL_HOLD, user) == 4000
    row = WithdrawalRequest.objects.get(pk=w["id"])
    delay = row.eligible_at - row.created_at
    assert abs(delay - timedelta(hours=WITHDRAW_FIRST_DELAY_HOURS)) < timedelta(seconds=5)
    assert row.payout_snapshot["number"] == "0245551234"
    pending = post(client, user, "/api/wallet/withdrawals", {"amount": 2000}).json()["error"]
    assert pending["code"] == "WITHDRAWAL_PENDING"
    post(client, user, f"/api/wallet/withdrawals/{w['id']}/cancel")
    assert ledger.balance(Kind.USER, user) == 10000
    assert ledger.balance(Kind.WITHDRAWAL_HOLD, user) == 0
    assert ledger.reconcile().ok


def test_payout_change_waits(client) -> None:
    user = player(funds=10000)
    post(client, user, "/api/wallet/payout-destination", DEST)
    changed = post(client, user, "/api/wallet/payout-destination", {**DEST, "number": "0249998888"})
    effective_at = NemesisProfile.objects.get(user=user).payout_effective_at
    assert changed.json()["payout"]["effective"] is False
    assert effective_at - timezone.now() > timedelta(hours=PAYOUT_CHANGE_DELAY_HOURS - 1)
    err = post(client, user, "/api/wallet/withdrawals", {"amount": 4000}).json()["error"]
    assert err["code"] == "PAYOUT_PENDING"


def test_withdrawal_minimum_funds_and_daily_cap(client) -> None:
    user = player(funds=WITHDRAW_DAILY_CAP * 2)
    post(client, user, "/api/wallet/payout-destination", DEST)
    small = post(client, user, "/api/wallet/withdrawals", {"amount": WITHDRAW_MIN - 1})
    assert small.json()["error"]["code"] == "INVALID_INPUT"
    over = post(client, user, "/api/wallet/withdrawals", {"amount": WITHDRAW_DAILY_CAP + 1})
    assert over.json()["error"]["code"] == "LIMIT_REACHED"
    poor = player(funds=1000)
    post(client, poor, "/api/wallet/payout-destination", DEST)
    err = post(client, poor, "/api/wallet/withdrawals", {"amount": WITHDRAW_MIN}).json()["error"]
    assert err["code"] == "INSUFFICIENT_FUNDS"
    assert not WithdrawalRequest.objects.filter(user=poor).exists()


def test_withdrawal_allowed_while_excluded_and_off(client) -> None:
    user = player(active=False, funds=10000)
    NemesisProfile.objects.filter(user=user).update(excluded_permanent=True)
    post(client, user, "/api/wallet/payout-destination", DEST)
    assert post(client, user, "/api/wallet/withdrawals", {"amount": 3000}).status_code == 201


# ----- limits and exclusion --------------------------------------------------------------


def test_lowering_is_immediate_raising_is_delayed(client) -> None:
    user = player()
    low = put(
        client, user, "/api/wallet/limits", {"depositDailyLimit": 5000, "deposit30dLimit": 20000}
    )
    assert low.json()["player"] == {"depositDaily": 5000, "deposit30d": 20000}
    assert low.json()["pendingRaise"] is None
    high = put(
        client, user, "/api/wallet/limits", {"depositDailyLimit": 9000, "deposit30dLimit": 10000}
    ).json()
    assert high["player"] == {"depositDaily": 5000, "deposit30d": 10000}
    assert high["pendingRaise"]["depositDailyLimit"] == 9000
    over = put(
        client,
        user,
        "/api/wallet/limits",
        {"depositDailyLimit": DEPOSIT_DAILY_LIMIT + 1, "deposit30dLimit": DEPOSIT_MIN},
    )
    assert over.json()["error"]["code"] == "INVALID_INPUT"
    profile = NemesisProfile.objects.get(user=user)
    profile.pending_limit_raise["effectiveAt"] = (
        timezone.now() - timedelta(hours=LIMIT_RAISE_DELAY_HOURS)
    ).isoformat()
    profile.save()
    later = client.get("/api/wallet", **auth(user)).json()["limits"]
    assert later["player"]["depositDaily"] == 9000 and later["pendingRaise"] is None


def test_exclusion_cannot_be_shortened(client) -> None:
    user = player()
    thirty = post(client, user, "/api/wallet/exclude", {"days": 30}).json()["exclusion"]
    seven = post(client, user, "/api/wallet/exclude", {"days": 7}).json()["exclusion"]
    assert seven["until"] == thirty["until"] and seven["active"]
    bad = post(client, user, "/api/wallet/exclude", {"days": 1})
    assert bad.json()["error"]["code"] == "INVALID_INPUT"
    perm = post(client, user, "/api/wallet/exclude", {"days": "permanent"}).json()["exclusion"]
    assert perm["permanent"] is True
