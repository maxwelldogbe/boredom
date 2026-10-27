"""Guest free-games quota: GUEST_FREE_GAMES game starts per GUEST_WINDOW_MS, per guest_key.

The window starts at a guest's first counted game; once it has run out, the next counted game
starts a new one. Times are epoch ms from the room manager's clock. Any database error fails
open: the guest is treated as unlocked and the error is logged.
"""

import logging
from collections.abc import Iterable
from typing import Any

from channels.db import database_sync_to_async
from django.db import transaction

from analytics.models import GuestQuota
from games.constants import GUEST_FREE_GAMES, GUEST_WINDOW_MS

logger = logging.getLogger("analytics.quota")


def status(row: GuestQuota | None, now: float) -> dict[str, Any]:
    """{remaining, limit, lockedUntil} for a row (None: no games counted yet)."""
    if row is None or now >= row.window_start + GUEST_WINDOW_MS:
        return {"remaining": GUEST_FREE_GAMES, "limit": GUEST_FREE_GAMES, "lockedUntil": None}
    remaining = max(0, GUEST_FREE_GAMES - row.plays)
    locked_until = row.window_start + GUEST_WINDOW_MS if remaining == 0 else None
    return {"remaining": remaining, "limit": GUEST_FREE_GAMES, "lockedUntil": locked_until}


def read_quota(keys: Iterable[str], now: float) -> dict[str, dict[str, Any]]:
    keys = list(keys)
    rows = {r.guest_key: r for r in GuestQuota.objects.filter(guest_key__in=keys)}
    return {key: status(rows.get(key), now) for key in keys}


def count_games(keys: Iterable[str], now: float) -> dict[str, dict[str, Any]]:
    """Count one game for each key; returns the new status of each."""
    out = {}
    with transaction.atomic():
        for key in keys:
            row, _ = GuestQuota.objects.select_for_update().get_or_create(
                guest_key=key, defaults={"window_start": int(now), "plays": 0}
            )
            if now >= row.window_start + GUEST_WINDOW_MS:
                row.window_start, row.plays = int(now), 0
            row.plays += 1
            row.save(update_fields=["window_start", "plays"])
            out[key] = status(row, now)
    return out


def prune_quota(now: float) -> int:
    """Delete rows whose window has run out (daily, with the activity retention)."""
    removed, _ = GuestQuota.objects.filter(window_start__lte=now - GUEST_WINDOW_MS).delete()
    return removed


class GuestQuotaStore:
    """Async access for the room manager. Missing keys in a result mean "not locked"."""

    async def read(self, keys: list[str], now: float) -> dict[str, dict[str, Any]]:
        if not keys:
            return {}
        try:
            return await database_sync_to_async(read_quota)(keys, now)
        except Exception:
            logger.exception("Guest quota read failed; allowing play")
            return {}

    async def count(self, keys: list[str], now: float) -> dict[str, dict[str, Any]]:
        if not keys:
            return {}
        try:
            return await database_sync_to_async(count_games)(keys, now)
        except Exception:
            logger.exception("Guest quota count failed; allowing play")
            return {}
