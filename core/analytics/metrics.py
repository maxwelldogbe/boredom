"""Dashboard metrics. Every number comes from ORM aggregation (no per-row queries).

Definitions (also in the README):
- A *completed* game is a GameSession with status "completed"; *abandoned* games are
  excluded from wins, losses and rates.
- Win = completed game with placement 1 (ties share the win). Loss = completed game with
  placement > 1 (players who forfeited or timed out count as losses).
- Win rate = wins / (wins + losses), shown only after DASHBOARD_MIN_GAMES_FOR_RATES
  completed games.
- An *actor* is a registered account (user) or a guest (guest_key, browser-based and so
  approximate).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from django.contrib.auth.models import User
from django.db.models import Avg, Count, Q, QuerySet
from django.db.models.functions import TruncDate
from django.utils import timezone

from analytics.models import ActivityEvent, GameParticipation, GameSession
from games import registry

COMPLETED = GameSession.Status.COMPLETED
ABANDONED = GameSession.Status.ABANDONED

RANGES = {"today": "Today", "7d": "Last 7 days", "30d": "Last 30 days", "all": "All time"}
DEFAULT_RANGE = "7d"


@dataclass(frozen=True)
class DateRange:
    key: str
    label: str
    since: datetime | None  # None = all time

    def session_q(self, prefix: str = "") -> Q:
        """Sessions started in range (`prefix` e.g. "session__")."""
        return Q(**{f"{prefix}started_at__gte": self.since}) if self.since else Q()

    def event_q(self) -> Q:
        return Q(occurred_at__gte=self.since) if self.since else Q()


def local_day_start(now: datetime) -> datetime:
    """Midnight today in the display TIME_ZONE."""
    return timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)


def parse_range(raw: str | None, now: datetime | None = None) -> DateRange:
    """The ?range= filter: today, 7d, 30d or all (default 7d)."""
    now = now or timezone.now()
    key = raw if raw in RANGES else DEFAULT_RANGE
    since = {
        "today": local_day_start(now),
        "7d": now - timedelta(days=7),
        "30d": now - timedelta(days=30),
        "all": None,
    }[key]
    return DateRange(key, RANGES[key], since)


def game_name(game_id: str) -> str:
    module = registry.get_game(game_id)
    return module.name if module else game_id


def known_game_ids() -> list[str]:
    return list(registry.all_games())


def unique_player_counts(participations: QuerySet[GameParticipation]) -> dict[str, int]:
    """Distinct users + distinct guests among completed-game participations, per game id."""
    return {
        r["session__game_id"]: r["users"] + r["guests"]
        for r in participations.filter(session__status=COMPLETED)
        .values("session__game_id")
        .annotate(
            users=Count("user", distinct=True),
            guests=Count("guest_key", distinct=True, filter=~Q(guest_key="")),
        )
    }


def ratio(part: float | None, whole: float | None) -> float | None:
    return part / whole if part is not None and whole else None


def session_aggregates(sessions: QuerySet[GameSession]) -> dict[str, Any]:
    """Completed / abandoned counts and completed-game averages for a session queryset."""
    done = Q(status=COMPLETED)
    agg = sessions.aggregate(
        completed=Count("id", filter=done),
        abandoned=Count("id", filter=Q(status=ABANDONED)),
        avg_players=Avg("player_count", filter=done),
        avg_duration=Avg("duration_seconds", filter=done),
    )
    agg["abandon_rate"] = ratio(agg["abandoned"], agg["completed"] + agg["abandoned"])
    agg["completion_rate"] = ratio(agg["completed"], agg["completed"] + agg["abandoned"])
    return agg


def plays_per_day(days: int, game_id: str | None = None, now: datetime | None = None):
    """[(date, completed games started that local day)] for the last `days` days."""
    now = now or timezone.now()
    tz = timezone.get_current_timezone()
    first: date = timezone.localdate(now, tz) - timedelta(days=days - 1)
    start = timezone.make_aware(datetime.combine(first, time.min), tz)
    sessions = GameSession.objects.filter(status=COMPLETED, started_at__gte=start)
    if game_id:
        sessions = sessions.filter(game_id=game_id)
    counts = {
        row["day"]: row["n"]
        for row in sessions.annotate(day=TruncDate("started_at", tzinfo=tz))
        .values("day")
        .annotate(n=Count("id"))
    }
    return [
        (first + timedelta(days=i), counts.get(first + timedelta(days=i), 0)) for i in range(days)
    ]


def overview(rng: DateRange, now: datetime | None = None) -> dict[str, Any]:
    """Everything on the Overview page except the live snapshot (cacheable)."""
    now = now or timezone.now()
    in_range = GameSession.objects.filter(rng.session_q())
    sessions = session_aggregates(in_range)
    sessions["today"] = GameSession.objects.filter(
        status=COMPLETED, started_at__gte=local_day_start(now)
    ).count()
    most = (
        in_range.filter(status=COMPLETED)
        .values("game_id")
        .annotate(n=Count("id"))
        .order_by("-n", "game_id")
        .first()
    )
    accounts = User.objects.filter(profile__isnull=False)
    users = accounts.aggregate(
        total=Count("id"),
        new=Count("id", filter=Q(date_joined__gte=rng.since) if rng.since else Q()),
    )
    guest_keys = (
        ActivityEvent.objects.filter(rng.event_q())
        .exclude(guest_key="")
        .values("guest_key")
        .union(
            GameParticipation.objects.filter(rng.session_q("session__"))
            .exclude(guest_key="")
            .values("guest_key")
        )
    )
    windows = {"daily": 1, "weekly": 7, "monthly": 30}
    active_q = {name: Q(occurred_at__gte=now - timedelta(days=d)) for name, d in windows.items()}
    counts = ActivityEvent.objects.filter(occurred_at__gte=now - timedelta(days=30)).aggregate(
        **{f"{n}_users": Count("user", distinct=True, filter=q) for n, q in active_q.items()},
        **{
            f"{n}_guests": Count("guest_key", distinct=True, filter=q & ~Q(guest_key=""))
            for n, q in active_q.items()
        },
    )
    active = {n: counts[f"{n}_users"] + counts[f"{n}_guests"] for n in windows}
    return {
        "sessions": sessions,
        "most_played": (
            {"id": most["game_id"], "name": game_name(most["game_id"]), "plays": most["n"]}
            if most
            else None
        ),
        "users": users,
        "guests_seen": guest_keys.count(),
        "active": active,
        "per_day": plays_per_day(30, now=now),
    }


def games_table(rng: DateRange) -> list[dict[str, Any]]:
    """One row per game: plays, unique players, averages, completion rate."""
    rows = {
        r["game_id"]: r
        for r in GameSession.objects.filter(rng.session_q())
        .values("game_id")
        .annotate(
            plays=Count("id", filter=Q(status=COMPLETED)),
            abandoned=Count("id", filter=Q(status=ABANDONED)),
            avg_players=Avg("player_count", filter=Q(status=COMPLETED)),
            avg_duration=Avg("duration_seconds", filter=Q(status=COMPLETED)),
        )
    }
    players = unique_player_counts(GameParticipation.objects.filter(rng.session_q("session__")))
    table = []
    for game_id in dict.fromkeys([*known_game_ids(), *rows]):
        row = rows.get(game_id, {})
        plays, abandoned = row.get("plays", 0), row.get("abandoned", 0)
        table.append(
            {
                "id": game_id,
                "name": game_name(game_id),
                "plays": plays,
                "abandoned": abandoned,
                "unique_players": players.get(game_id, 0),
                "avg_players": row.get("avg_players"),
                "avg_duration": row.get("avg_duration"),
                "completion_rate": ratio(plays, plays + abandoned),
            }
        )
    table.sort(key=lambda r: (-r["plays"], r["name"]))
    return table


def game_detail(game_id: str, rng: DateRange) -> dict[str, Any]:
    sessions = GameSession.objects.filter(rng.session_q(), game_id=game_id)
    totals = session_aggregates(sessions)
    totals["unique_players"] = unique_player_counts(
        GameParticipation.objects.filter(rng.session_q("session__"), session__game_id=game_id)
    ).get(game_id, 0)
    recent = list(
        GameSession.objects.filter(game_id=game_id)
        .order_by("-started_at")
        .values("id", "status", "started_at", "duration_seconds", "player_count", "room_code")[:20]
    )
    return {
        "id": game_id,
        "name": game_name(game_id),
        "totals": totals,
        "per_day": plays_per_day(30, game_id),
        "recent": recent,
    }
