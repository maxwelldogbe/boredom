"""Brag coin rules: the starter grant, Hard-bot rewards with their caps, and the history.

Every change goes through `_apply` in one transaction with the wallet row locked, so the
balance and the ledger always agree and never go below 0.
"""

import logging
from datetime import datetime, time
from typing import Any

from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from brag.models import BragEntry, BragWallet
from games.constants import BRAG_DAILY_CAP, BRAG_HARD_REWARDS, BRAG_STARTER, BRAG_WIN_CAP

logger = logging.getLogger("brag.services")

HISTORY_SIZE = 20


def hard_reward(game_id: str, size: int | None = None) -> int:
    """Coins a Hard bot win pays (Dots and Boxes by board size), at most BRAG_WIN_CAP."""
    key = f"{game_id}:{size}x{size}" if game_id == "dots_and_boxes" else game_id
    return min(BRAG_HARD_REWARDS.get(key, 0), BRAG_WIN_CAP)


def _wallet(user_id: int) -> BragWallet:
    """The locked wallet, created with the starter grant the first time (inside a transaction)."""
    wallet, created = BragWallet.objects.select_for_update().get_or_create(user_id=user_id)
    if created and BRAG_STARTER:
        wallet.balance = BRAG_STARTER
        wallet.save(update_fields=["balance"])
        BragEntry.objects.create(
            user_id=user_id,
            amount=BRAG_STARTER,
            balance_after=wallet.balance,
            kind=BragEntry.Kind.STARTER,
        )
    return wallet


def _apply(wallet: BragWallet, amount: int, kind: str, game_id: str = "", ref: str = "") -> None:
    wallet.balance += amount
    if wallet.balance < 0:
        raise ValueError("Not enough Brag coins.")
    wallet.save(update_fields=["balance"])
    BragEntry.objects.create(
        user_id=wallet.user_id,
        amount=amount,
        balance_after=wallet.balance,
        kind=kind,
        game_id=game_id,
        ref=ref,
    )


def _today_start() -> datetime:
    now = timezone.localtime()
    return timezone.make_aware(datetime.combine(now.date(), time.min), now.tzinfo)


def earned_today(user_id: int) -> int:
    """Coins from bot wins since midnight (server time zone)."""
    rows = BragEntry.objects.filter(
        user_id=user_id, kind=BragEntry.Kind.BOT_WIN, created_at__gte=_today_start()
    )
    return rows.aggregate(total=Sum("amount"))["total"] or 0


def reward_bot_win(user_id: int, game_id: str, size: int | None = None) -> dict[str, int] | None:
    """Pay a Hard bot win, within BRAG_DAILY_CAP. None if the account is gone."""
    with transaction.atomic():
        if not User.objects.filter(pk=user_id, is_active=True).exists():
            return None
        wallet = _wallet(user_id)
        room_left = max(0, BRAG_DAILY_CAP - earned_today(user_id))
        awarded = min(hard_reward(game_id, size), room_left)
        if awarded:
            _apply(wallet, awarded, BragEntry.Kind.BOT_WIN, game_id)
        return {
            "awarded": awarded,
            "balance": wallet.balance,
            "dailyLeft": room_left - awarded,
            "dailyCap": BRAG_DAILY_CAP,
        }


def balance(user_id: int) -> int:
    with transaction.atomic():
        return _wallet(user_id).balance


def hold_stake(user_id: int, amount: int, game_id: str, ref: str) -> bool:
    """Take a stake from the wallet; False (nothing taken) if the balance is too low."""
    with transaction.atomic():
        if not User.objects.filter(pk=user_id, is_active=True).exists():
            return False
        wallet = _wallet(user_id)
        if wallet.balance < amount:
            return False
        _apply(wallet, -amount, BragEntry.Kind.STAKE, game_id, ref)
        return True


def credit(user_id: int, amount: int, kind: str, game_id: str, ref: str) -> None:
    """Pay a pot share or return a stake (skipped for a deleted account)."""
    if amount <= 0:
        return
    with transaction.atomic():
        if not User.objects.filter(pk=user_id).exists():
            return
        _apply(_wallet(user_id), amount, kind, game_id, ref)


def summary(user: User) -> dict[str, Any]:
    """GET /api/brag: balance, today's bot earnings, the reward table and recent history."""
    with transaction.atomic():
        wallet = _wallet(user.pk)
    today = earned_today(user.pk)
    entries = BragEntry.objects.filter(user=user).order_by("-created_at", "-id")[:HISTORY_SIZE]
    return {
        "balance": wallet.balance,
        "earnedToday": today,
        "dailyCap": BRAG_DAILY_CAP,
        "rewards": dict(BRAG_HARD_REWARDS),
        "history": [
            {
                "amount": e.amount,
                "balanceAfter": e.balance_after,
                "kind": e.kind,
                "gameId": e.game_id or None,
                "at": e.created_at.isoformat(),
            }
            for e in entries
        ],
    }


class BragStore:
    """Async access for the room manager. Rewards fail open (logged, None); a stake that can't
    be taken is treated as not taken, so nobody plays a staked game without paying."""

    async def balance(self, user_id: int) -> int | None:
        try:
            return await database_sync_to_async(balance)(user_id)
        except Exception:
            logger.exception("Brag balance failed")
            return None

    async def hold_stake(self, user_id: int, amount: int, game_id: str, ref: str) -> bool:
        try:
            return await database_sync_to_async(hold_stake)(user_id, amount, game_id, ref)
        except Exception:
            logger.exception("Brag stake failed: ref=%s", ref)
            return False

    async def credit(self, user_id: int, amount: int, kind: str, game_id: str, ref: str) -> None:
        try:
            await database_sync_to_async(credit)(user_id, amount, kind, game_id, ref)
        except Exception:
            logger.exception("Brag credit failed: ref=%s kind=%s amount=%s", ref, kind, amount)

    async def reward_bot_win(
        self, user_id: int, game_id: str, size: int | None = None
    ) -> dict[str, int] | None:
        try:
            return await database_sync_to_async(reward_bot_win)(user_id, game_id, size)
        except Exception:
            logger.exception("Brag reward failed: game=%s", game_id)
            return None
