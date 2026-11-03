"""Nemesis ledger (zero-sum, overdraw, idempotency, locking, reconcile) and wallet reads."""

import itertools
import threading

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection
from django.test import Client

from accounts.tokens import issue_token
from games.constants import WALLET_PAGE_SIZE
from nemesis import ledger
from nemesis.ledger import LedgerError
from nemesis.models import LedgerAccount, LedgerEntry
from tests.nemesis_helpers import account_user

Kind = LedgerAccount.Kind
_names = itertools.count(1)


def deposit(user: User, amount: int, key: str | None = None):
    return ledger.post_transaction(
        "deposit",
        key or f"test-deposit:{next(_names)}",
        [(ledger.account(Kind.EXTERNAL), -amount), (ledger.account(Kind.USER, user), amount)],
    )


def hold(user: User, amount: int, key: str):
    return ledger.post_transaction(
        "withdrawal_hold",
        key,
        [
            (ledger.account(Kind.USER, user), -amount),
            (ledger.account(Kind.WITHDRAWAL_HOLD, user), amount),
        ],
    )


@pytest.mark.django_db
def test_entries_must_sum_to_zero() -> None:
    user = account_user()
    with pytest.raises(ValueError):
        ledger.post_transaction(
            "deposit",
            "k1",
            [(ledger.account(Kind.EXTERNAL), -100), (ledger.account(Kind.USER, user), 99)],
        )
    assert LedgerEntry.objects.count() == 0


@pytest.mark.django_db
def test_overdraw_is_rejected_and_changes_nothing() -> None:
    user = account_user()
    deposit(user, 1000)
    with pytest.raises(LedgerError) as exc:
        hold(user, 1001, "hold-1")
    assert exc.value.code == "INSUFFICIENT_FUNDS"
    assert ledger.balance(Kind.USER, user) == 1000
    assert ledger.balance(Kind.WITHDRAWAL_HOLD, user) == 0
    assert ledger.reconcile().ok


@pytest.mark.django_db
def test_same_idempotency_key_posts_once() -> None:
    user = account_user()
    first = deposit(user, 500, key="deposit:1")
    again = deposit(user, 500, key="deposit:1")
    assert again.pk == first.pk
    assert ledger.balance(Kind.USER, user) == 500
    assert LedgerEntry.objects.count() == 2


@pytest.mark.django_db
def test_entries_are_immutable() -> None:
    user = account_user()
    deposit(user, 500)
    entry = LedgerEntry.objects.first()
    with pytest.raises(TypeError):
        entry.save()
    with pytest.raises(TypeError):
        LedgerEntry.objects.all().update(amount=1)
    with pytest.raises(TypeError):
        LedgerEntry.objects.all().delete()


@pytest.mark.django_db
def test_reconcile_catches_a_tampered_balance() -> None:
    user = account_user()
    deposit(user, 700)
    assert ledger.reconcile().ok
    assert ledger.liabilities() == 700
    call_command("check_ledger")
    LedgerAccount.objects.filter(kind=Kind.USER, user=user).update(balance=900)
    result = ledger.reconcile()
    assert not result.ok
    assert result.mismatched_accounts[0]["cached"] == 900
    with pytest.raises(CommandError):
        call_command("check_ledger")


@pytest.mark.django_db(transaction=True)
def test_concurrent_holds_cannot_overdraw() -> None:
    if connection.vendor != "postgresql":
        pytest.skip(
            "Concurrency test needs PostgreSQL (set DATABASE_URL); SQLite has no row locks."
        )
    user = account_user()
    deposit(user, 1000)
    results: list[str] = []

    def worker(i: int) -> None:
        try:
            hold(user, 600, f"hold-{i}")
            results.append("ok")
        except LedgerError as exc:
            results.append(exc.code)
        finally:
            close_old_connections()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 1
    assert ledger.balance(Kind.USER, user) == 400
    assert ledger.reconcile().ok


# ----- Wallet endpoints ------------------------------------------------------------------


def get(client: Client, path: str, user: User):
    return client.get(path, HTTP_AUTHORIZATION=f"Bearer {issue_token(user.pk)}")


@pytest.mark.django_db
def test_disabled_only_status_answers(client: Client, settings) -> None:
    settings.NEMESIS_ENABLED = False
    user = account_user()
    res = get(client, "/api/nemesis/status", user)
    assert res.status_code == 200 and res.json() == {"enabled": False}
    assert res["Cache-Control"] == "no-store"
    for path in ("/api/wallet", "/api/wallet/entries"):
        assert get(client, path, user).status_code == 404


@pytest.mark.django_db
def test_wallet_needs_a_token(client: Client, settings) -> None:
    settings.NEMESIS_ENABLED = True
    assert client.get("/api/wallet").status_code == 401


@pytest.mark.django_db
def test_wallet_and_paged_entries(client: Client, settings) -> None:
    settings.NEMESIS_ENABLED = True
    user = account_user()
    for _ in range(WALLET_PAGE_SIZE):
        deposit(user, 1000)
    hold(user, 3000, "hold-w")
    body = get(client, "/api/wallet", user).json()
    assert body["balance"] == WALLET_PAGE_SIZE * 1000 - 3000
    assert body["held"] == 3000
    assert body["currency"] == "GHS"
    assert body["flags"] == {
        "depositsEnabled": True,
        "withdrawalsEnabled": True,
        "stakingEnabled": False,
    }
    first = get(client, "/api/wallet/entries", user).json()
    assert len(first["entries"]) == WALLET_PAGE_SIZE
    assert first["entries"][0]["kind"] == "withdrawal_hold"
    assert first["entries"][0]["amount"] == -3000
    second = get(client, f"/api/wallet/entries?cursor={first['nextCursor']}", user).json()
    assert len(second["entries"]) == 1 and second["nextCursor"] is None
