"""Solo records: the upsert after a solo game and the list for GET /api/solo/records."""

import logging
from typing import Any

from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F

from solo.models import SoloRecord

logger = logging.getLogger("solo.services")

OUTCOME_FIELDS = {"win": "wins", "lose": "losses", "draw": "draws"}


def record_outcome(user_id: int, game_id: str, variant: str, outcome: str) -> dict[str, int] | None:
    """One more play (and win, loss or draw) in one transaction. None if the account is gone."""
    with transaction.atomic():
        if not User.objects.filter(pk=user_id).exists():
            return None
        SoloRecord.objects.get_or_create(user_id=user_id, game_id=game_id, variant=variant)
        rows = SoloRecord.objects.filter(user_id=user_id, game_id=game_id, variant=variant)
        counter = OUTCOME_FIELDS[outcome]
        rows.update(plays=F("plays") + 1, **{counter: F(counter) + 1})
        record = rows.get()
    return {
        "plays": record.plays,
        "wins": record.wins,
        "losses": record.losses,
        "draws": record.draws,
    }


def record_score(user_id: int, game_id: str, variant: str, score: int) -> dict[str, int] | None:
    """One more run: plays + 1 and best_score = max(best, score). None if the account is gone.

    The result also holds `previousBest`, the best before this run.
    """
    with transaction.atomic():
        if not User.objects.filter(pk=user_id).exists():
            return None
        SoloRecord.objects.get_or_create(user_id=user_id, game_id=game_id, variant=variant)
        record = SoloRecord.objects.select_for_update().get(
            user_id=user_id, game_id=game_id, variant=variant
        )
        previous = record.best_score
        record.plays += 1
        record.best_score = max(previous, score)
        record.save(update_fields=["plays", "best_score", "updated_at"])
    return {"plays": record.plays, "bestScore": record.best_score, "previousBest": previous}


def records_for(user: User) -> list[dict[str, Any]]:
    """Every solo record of `user`, by game then variant."""
    return [
        {
            "gameId": r.game_id,
            "variant": r.variant,
            "plays": r.plays,
            "wins": r.wins,
            "losses": r.losses,
            "draws": r.draws,
            "bestScore": r.best_score,
        }
        for r in SoloRecord.objects.filter(user=user).order_by("game_id", "variant")
    ]


class SoloRecordStore:
    """Async access for the room manager. Fails open: an error is logged and None returned."""

    async def record(
        self, user_id: int, game_id: str, variant: str, outcome: str
    ) -> dict[str, int] | None:
        try:
            return await database_sync_to_async(record_outcome)(user_id, game_id, variant, outcome)
        except Exception:
            logger.exception("Solo record failed: game=%s variant=%s", game_id, variant)
            return None

    async def record_score(
        self, user_id: int, game_id: str, variant: str, score: int
    ) -> dict[str, int] | None:
        try:
            return await database_sync_to_async(record_score)(user_id, game_id, variant, score)
        except Exception:
            logger.exception("Solo score failed: game=%s variant=%s", game_id, variant)
            return None
