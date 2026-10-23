"""Activity retention: ActivityEvent rows older than ACTIVITY_RETENTION_DAYS are deleted.

Game sessions and participations are never deleted (they hold the totals).
"""

from datetime import datetime, timedelta

from django.utils import timezone

from analytics.models import ActivityEvent
from games.constants import ACTIVITY_RETENTION_DAYS


def prune_events(now: datetime | None = None) -> int:
    """Delete expired events. Returns how many were removed."""
    cutoff = (now or timezone.now()) - timedelta(days=ACTIVITY_RETENTION_DAYS)
    removed, _ = ActivityEvent.objects.filter(occurred_at__lt=cutoff).delete()
    return removed
