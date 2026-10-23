"""Account data: the saved profile and per-game stats of a registered player.

Rooms and games stay in memory; only accounts live in the database.
"""

from django.conf import settings
from django.db import models

from games.constants import NICKNAME_MAX

COLOR_LENGTH = 7  # "#RRGGBB"
AVATAR_FIELD_MAX = 32
GAME_ID_MAX = 32


class Profile(models.Model):
    """The saved profile used in every room. The avatar is kept forever once claimed."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    nickname = models.CharField(max_length=NICKNAME_MAX)
    color = models.CharField(max_length=COLOR_LENGTH)
    avatar_style = models.CharField(max_length=AVATAR_FIELD_MAX)
    avatar_seed = models.CharField(max_length=AVATAR_FIELD_MAX)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.nickname


class PlayerStats(models.Model):
    """Games played and won by one account in one game. Wins are placement-1 finishes."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="stats"
    )
    game_id = models.CharField(max_length=GAME_ID_MAX)
    played = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "game_id"], name="stats_unique_user_game"),
            models.CheckConstraint(
                condition=models.Q(wins__lte=models.F("played")), name="stats_wins_lte_played"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.game_id} {self.wins}/{self.played}"
