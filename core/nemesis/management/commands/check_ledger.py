"""`python manage.py check_ledger`: verify the ledger is zero-sum and its cached balances.

Exits with an error (and lists the problems) when anything is off.
"""

from django.core.management.base import BaseCommand, CommandError

from nemesis import ledger


class Command(BaseCommand):
    help = "Check that ledger entries sum to zero and cached balances match their entries."

    def handle(self, *args, **options) -> None:
        result = ledger.reconcile()
        self.stdout.write(f"Entries sum: {result.entries_sum}")
        self.stdout.write(f"Unbalanced transactions: {result.unbalanced_transactions}")
        self.stdout.write(f"Liabilities (pesewas): {result.liabilities}")
        for row in result.mismatched_accounts:
            self.stdout.write(
                f"Mismatch: account {row['accountId']} ({row['kind']}) "
                f"cached {row['cached']} vs entries {row['entries']}"
            )
        if not result.ok:
            raise CommandError("Ledger check FAILED.")
        self.stdout.write(self.style.SUCCESS("Ledger OK."))
