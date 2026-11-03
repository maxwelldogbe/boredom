"""The double-entry ledger: the ONLY code that changes LedgerAccount balances.

Signed and zero-sum. A deposit moves value from `external` (which goes negative: money we
hold for players) to the user; a withdrawal request moves user -> withdrawal_hold; paying out
moves withdrawal_hold -> external; a rejection moves it back. Escrow and fees are for Part 2.
Amounts are integers in pesewas. Written for PostgreSQL row locks (select_for_update).
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Sum

from nemesis.errors import NemesisError
from nemesis.models import LedgerAccount, LedgerEntry, LedgerTransaction

Kind = LedgerAccount.Kind
SYSTEM_KINDS = (Kind.EXTERNAL, Kind.ESCROW, Kind.FEES)
LIABILITY_KINDS = (Kind.USER, Kind.ESCROW, Kind.WITHDRAWAL_HOLD, Kind.FEES)


class LedgerError(NemesisError):
    """A rejected posting (INSUFFICIENT_FUNDS)."""


def account(kind: str, user: User | None = None) -> LedgerAccount:
    """The account of `kind` (for `user`, or the system one), created on first use."""
    if (kind in SYSTEM_KINDS) != (user is None):
        raise ValueError(f"{kind} accounts {'have no' if user is None else 'need a'} user")
    try:
        with transaction.atomic():
            return LedgerAccount.objects.get_or_create(kind=kind, user=user)[0]
    except IntegrityError:  # created concurrently
        return LedgerAccount.objects.get(kind=kind, user=user)


def balance(kind: str, user: User) -> int:
    """A user account's cached balance (0 if it was never used). Never creates the account."""
    row = LedgerAccount.objects.filter(kind=kind, user=user).values_list("balance", flat=True)
    return row.first() or 0


def _is_amount(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value != 0


def post_transaction(
    kind: str,
    idempotency_key: str,
    entries: Iterable[tuple[LedgerAccount, int]],
    meta: dict[str, Any] | None = None,
) -> LedgerTransaction:
    """Post balanced `entries` [(account, signed amount)] as one transaction.

    Locks every involved account (ascending id, so concurrent postings cannot deadlock), then
    checks the key: if it was already used the existing transaction is returned and nothing
    changes. Raises LedgerError(INSUFFICIENT_FUNDS) if any non-external account would go below
    zero, and ValueError for entries that are not nonzero integers summing to exactly zero.
    """
    entries = list(entries)
    if len(entries) < 2 or not all(_is_amount(amount) for _, amount in entries):
        raise ValueError("A transaction needs two or more nonzero integer entries.")
    if sum(amount for _, amount in entries) != 0:
        raise ValueError("Ledger entries must sum to zero.")
    if not idempotency_key:
        raise ValueError("An idempotency key is required.")

    with transaction.atomic():
        ids = sorted({acc.pk for acc, _ in entries})
        locked = {
            a.pk: a
            for a in LedgerAccount.objects.select_for_update().filter(pk__in=ids).order_by("pk")
        }
        existing = LedgerTransaction.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing

        balances = {pk: acc.balance for pk, acc in locked.items()}
        lines = []
        for acc, amount in entries:
            balances[acc.pk] += amount
            if locked[acc.pk].kind != Kind.EXTERNAL and balances[acc.pk] < 0:
                raise LedgerError("INSUFFICIENT_FUNDS", "Not enough funds.")
            lines.append((acc.pk, amount, balances[acc.pk]))

        tx = LedgerTransaction.objects.create(
            kind=kind, idempotency_key=idempotency_key, meta=meta or {}
        )
        LedgerEntry.objects.bulk_create(
            LedgerEntry(transaction=tx, account_id=pk, amount=amount, balance_after=after)
            for pk, amount, after in lines
        )
        for pk, new_balance in balances.items():
            if new_balance != locked[pk].balance:
                LedgerAccount.objects.filter(pk=pk).update(balance=new_balance)
                locked[pk].balance = new_balance
        return tx


def liabilities() -> int:
    """What we owe: user + escrow + withdrawal_hold + fees balances (pesewas)."""
    total = LedgerAccount.objects.filter(kind__in=LIABILITY_KINDS).aggregate(s=Sum("balance"))
    return total["s"] or 0


@dataclass
class Reconciliation:
    ok: bool
    entries_sum: int
    unbalanced_transactions: int
    mismatched_accounts: list[dict[str, Any]] = field(default_factory=list)
    liabilities: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "entriesSum": self.entries_sum,
            "unbalancedTransactions": self.unbalanced_transactions,
            "mismatchedAccounts": self.mismatched_accounts,
            "liabilities": self.liabilities,
        }


def reconcile() -> Reconciliation:
    """Check that all entries (and each transaction) sum to zero and caches match entry sums."""
    entries_sum = LedgerEntry.objects.aggregate(s=Sum("amount"))["s"] or 0
    unbalanced = (
        LedgerEntry.objects.values("transaction").annotate(s=Sum("amount")).exclude(s=0).count()
    )
    sums: dict[int, int] = defaultdict(int)
    for row in LedgerEntry.objects.values("account").annotate(s=Sum("amount")):
        sums[row["account"]] = row["s"]
    mismatched = [
        {"accountId": acc.pk, "kind": acc.kind, "cached": acc.balance, "entries": sums[acc.pk]}
        for acc in LedgerAccount.objects.order_by("pk")
        if acc.balance != sums[acc.pk]
    ]
    return Reconciliation(
        ok=entries_sum == 0 and unbalanced == 0 and not mismatched,
        entries_sum=entries_sum,
        unbalanced_transactions=unbalanced,
        mismatched_accounts=mismatched,
        liabilities=liabilities(),
    )
