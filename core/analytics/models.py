"""Activity records for the admin dashboard. Times are stored in UTC.

Nothing here holds a raw profile id, IP address, user agent, password, token or game secret.
Guests are identified only by `guest_key` (see analytics.keys).
"""

from django.conf import settings
from django.db import models

GAME_ID_MAX = 32
ROOM_CODE_MAX = 8
NICKNAME_SNAPSHOT_MAX = 32  # room nicknames are shorter; "Deleted player" must fit
DELETED_NICKNAME = "Deleted player"


class GameSession(models.Model):
    """One game played in a room, from game:start to its end."""

    class Status(models.TextChoices):
        COMPLETED = "completed"
        ABANDONED = "abandoned"

    game_id = models.CharField(max_length=GAME_ID_MAX)
    room_code = models.CharField(max_length=ROOM_CODE_MAX)
    settings = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    duration_seconds = models.PositiveIntegerField()
    player_count = models.PositiveSmallIntegerField()

    class Meta:
        indexes = [
            models.Index(fields=["game_id", "started_at"], name="session_game_started"),
            models.Index(fields=["status", "started_at"], name="session_status_started"),
            models.Index(fields=["started_at"], name="session_started"),
        ]

    def __str__(self) -> str:
        return f"{self.game_id} {self.status} {self.started_at:%Y-%m-%d %H:%M}"


class GameParticipation(models.Model):
    """One seat in one game session. `placement` is null when the game was abandoned."""

    class PlayerType(models.TextChoices):
        GUEST = "guest"
        REGISTERED = "registered"

    session = models.ForeignKey(
        GameSession, on_delete=models.CASCADE, related_name="participations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="participations",
    )
    guest_key = models.CharField(max_length=32, blank=True)
    player_type = models.CharField(max_length=16, choices=PlayerType.choices)
    nickname = models.CharField(max_length=NICKNAME_SNAPSHOT_MAX)
    placement = models.PositiveSmallIntegerField(null=True, blank=True)
    raw_score = models.FloatField(null=True, blank=True)
    session_points = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    is_win = models.BooleanField(default=False)
    left_early = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["user", "session"], name="part_user_session"),
            models.Index(fields=["guest_key", "session"], name="part_guest_session"),
            models.Index(fields=["session", "placement"], name="part_session_placement"),
            models.Index(fields=["is_win", "placement"], name="part_win_placement"),
        ]

    def __str__(self) -> str:
        return f"{self.nickname} #{self.placement}"


class ActivityEvent(models.Model):
    """A notable account or room moment. Per-action game events are never recorded."""

    class Kind(models.TextChoices):
        SIGNUP = "signup"
        LOGIN = "login"
        LOGIN_FAILED = "login_failed"
        ACCOUNT_DELETED = "account_deleted"
        ROOM_CREATED = "room_created"
        ROOM_JOINED = "room_joined"
        ROOM_LEFT = "room_left"
        GAME_STARTED = "game_started"
        GAME_FINISHED = "game_finished"
        GAME_ABANDONED = "game_abandoned"

    kind = models.CharField(max_length=32, choices=Kind.choices)
    occurred_at = models.DateTimeField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_events",
    )
    guest_key = models.CharField(max_length=32, blank=True)
    room_code = models.CharField(max_length=ROOM_CODE_MAX, blank=True)
    game_id = models.CharField(max_length=GAME_ID_MAX, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "occurred_at"], name="event_user_time"),
            models.Index(fields=["guest_key", "occurred_at"], name="event_guest_time"),
            models.Index(fields=["kind", "occurred_at"], name="event_kind_time"),
            models.Index(fields=["occurred_at"], name="event_time"),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.occurred_at:%Y-%m-%d %H:%M}"
