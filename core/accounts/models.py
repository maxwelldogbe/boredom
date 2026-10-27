"""Account data: the saved profile and per-game stats of a registered player.

Rooms and games stay in memory; only accounts live in the database.
"""

from django.conf import settings
from django.db import models

from games.constants import NICKNAME_MAX, TAG_LENGTH

COLOR_LENGTH = 7  # "#RRGGBB"
AVATAR_FIELD_MAX = 32
GAME_ID_MAX = 32


class Profile(models.Model):
    """The profile used in every room. The avatar changes at most once per AVATAR_CHANGE_DAYS."""

    class PresenceMode(models.TextChoices):
        ONLINE = "online"
        BUSY = "busy"
        OFFLINE = "offline"  # "appear offline" to friends

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    nickname = models.CharField(max_length=NICKNAME_MAX)
    color = models.CharField(max_length=COLOR_LENGTH)
    avatar_style = models.CharField(max_length=AVATAR_FIELD_MAX)
    avatar_seed = models.CharField(max_length=AVATAR_FIELD_MAX)
    created_at = models.DateTimeField(auto_now_add=True)
    # When the player last picked a new avatar; null means never (a change is allowed now).
    avatar_changed_at = models.DateTimeField(null=True, blank=True)
    # Public "#K7M2QX" code: assigned once (accounts.tags), never changes. Null only until the
    # backfill migration has run; unique among the rest.
    tag = models.CharField(max_length=TAG_LENGTH, unique=True, null=True, blank=True)
    # What friends see (social.presence); set through PATCH /api/me/settings.
    presence_mode = models.CharField(
        max_length=8, choices=PresenceMode.choices, default=PresenceMode.ONLINE
    )

    def __str__(self) -> str:
        return self.nickname


class TakenTag(models.Model):
    """Every tag ever issued. Rows are never deleted, so a deleted account's tag is never reused."""

    tag = models.CharField(max_length=TAG_LENGTH, primary_key=True)
    issued_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.tag


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
