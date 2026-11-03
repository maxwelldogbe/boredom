"""Solo results: one row per account, game and variant (for bot games, the difficulty).

Solo rooms stay in memory like every room; only these totals live in the database. They
never touch PlayerStats, analytics sessions or anything else multiplayer games record.
"""

from django.conf import settings
from django.db import models

from accounts.models import GAME_ID_MAX

VARIANT_MAX = 16


class SoloRecord(models.Model):
    """Games played, won, lost and drawn alone. `best_score` is for challenge games."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="solo_records"
    )
    game_id = models.CharField(max_length=GAME_ID_MAX)
    variant = models.CharField(max_length=VARIANT_MAX)
    plays = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    draws = models.PositiveIntegerField(default=0)
    best_score = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "game_id", "variant"], name="solo_unique_user_game_variant"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.game_id}/{self.variant} {self.wins}/{self.plays}"
