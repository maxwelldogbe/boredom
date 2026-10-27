"""Friendships, friend requests, blocks and reports between registered accounts.

Deleting an account cascades its friendships, requests and blocks; reports are kept with the
account links set to null and the nickname snapshot intact.
"""

from django.conf import settings
from django.db import models

from games.constants import GUEST_KEY_LENGTH, NICKNAME_MAX, REPORT_NOTE_MAX, REPORT_REASONS

ROOM_CODE_MAX = 8
GAME_ID_MAX = 32
RESOLVED_NOTE_MAX = 500


class Friendship(models.Model):
    """Two friends, stored once as an ordered pair (user_low.pk < user_high.pk)."""

    user_low = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    user_high = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user_low", "user_high"], name="friendship_unique"),
            models.CheckConstraint(
                condition=models.Q(user_low__lt=models.F("user_high")), name="friendship_ordered"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_low_id}<->{self.user_high_id}"


class FriendRequest(models.Model):
    """A pending request. Accepting, declining or cancelling deletes the row."""

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["from_user", "to_user"], name="friend_request_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.from_user_id}->{self.to_user_id}"


class Block(models.Model):
    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["blocker", "blocked"], name="block_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.blocker_id} blocks {self.blocked_id}"


class Report(models.Model):
    """A player report for staff. The note is admin-only and never shown to other players.

    The reported player is a registered account (`reported_user`) or a guest seat
    (`reported_guest_key`, the pseudonymous analytics key). `reported_nickname` is a snapshot.
    """

    class Status(models.TextChoices):
        OPEN = "open"
        RESOLVED = "resolved"
        DISMISSED = "dismissed"

    Reason = models.TextChoices("Reason", [(r, r) for r in REPORT_REASONS])

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    reported_guest_key = models.CharField(max_length=GUEST_KEY_LENGTH, blank=True)
    reported_nickname = models.CharField(max_length=NICKNAME_MAX)
    reason = models.CharField(max_length=32, choices=Reason.choices)
    note = models.CharField(max_length=REPORT_NOTE_MAX, blank=True)
    room_code = models.CharField(max_length=ROOM_CODE_MAX, blank=True)
    game_id = models.CharField(max_length=GAME_ID_MAX, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    resolved_note = models.CharField(max_length=RESOLVED_NOTE_MAX, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "-created_at"])]

    def __str__(self) -> str:
        return f"Report {self.pk} ({self.reason}, {self.status})"
