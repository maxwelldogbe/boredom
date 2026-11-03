"""Brag coins: a wallet per account and an append-only ledger of every change.

Play money only: no purchase, no cash-out, no transfer, no link to the Nemesis wallet.
"""

from django.conf import settings
from django.db import models

from accounts.models import GAME_ID_MAX


class BragWallet(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="brag_wallet"
    )
    balance = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(balance__gte=0), name="brag_balance_gte_0")
        ]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.balance}"


class BragEntry(models.Model):
    """One change to a wallet. Rows are never edited or deleted (until the account is)."""

    class Kind(models.TextChoices):
        STARTER = "starter"  # the grant every account gets once
        BOT_WIN = "bot_win"  # a Hard bot beaten in a solo game
        STAKE = "stake"  # held when a staked game starts (negative)
        POT_WIN = "pot_win"  # the pot of a staked game won
        STAKE_REFUND = "stake_refund"  # a staked game that ended without a winner

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="brag_entries"
    )
    amount = models.IntegerField()  # positive in, negative out
    balance_after = models.IntegerField()
    kind = models.CharField(max_length=16, choices=Kind.choices)
    game_id = models.CharField(max_length=GAME_ID_MAX, blank=True)
    ref = models.CharField(max_length=64, blank=True)  # e.g. the room code of a staked game
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"], name="brag_user_time"),
            models.Index(fields=["user", "kind", "created_at"], name="brag_user_kind_time"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.kind} {self.amount:+d}"
