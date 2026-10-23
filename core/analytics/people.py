"""Per-actor metrics: the Users list, user detail and leaderboards.

An actor is a registered account (user) or a guest (guest_key). Participations of deleted
accounts have neither and are left out of per-actor views (they still count in game totals).
"""

from dataclasses import dataclass
from typing import Any

from django.contrib.auth.models import User
from django.db.models import (
    Avg,
    Case,
    CharField,
    Count,
    F,
    FloatField,
    IntegerField,
    Max,
    Min,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Cast, Coalesce, Greatest

from analytics.metrics import COMPLETED, game_name
from analytics.models import ActivityEvent, GameParticipation
from games.constants import DASHBOARD_MIN_GAMES_FOR_RATES

ROW_FIELDS = (
    "row_key",
    "row_kind",
    "row_user_id",
    "row_username",
    "row_nickname",
    "first_seen",
    "last_seen",
    "games",
    "wins",
    "win_rate",
    "favorite",
)
SORTS = {"games": "games", "wins": "wins", "win_rate": "win_rate", "last_seen": "last_seen"}
DEFAULT_SORT = "games"
KNOWN = ~Q(user__isnull=True, guest_key="")  # excludes deleted accounts' participations


def rate_expr() -> Case:
    """wins / games once the actor has DASHBOARD_MIN_GAMES_FOR_RATES completed games."""
    return Case(
        When(
            games__gte=DASHBOARD_MIN_GAMES_FOR_RATES,
            then=Cast("wins", FloatField()) / Cast("games", FloatField()),
        ),
        default=None,
        output_field=FloatField(),
    )


def show_rate(games: int, wins: int) -> float | None:
    return wins / games if games >= DASHBOARD_MIN_GAMES_FOR_RATES else None


def _count(filter_: Q) -> Subquery:
    return Subquery(
        GameParticipation.objects.filter(filter_)
        .values("user")
        .annotate(c=Count("id"))
        .values("c")[:1],
        output_field=IntegerField(),
    )


def _favorite(filter_: Q, group: str) -> Subquery:
    """Most-played completed game (ties: lowest game id)."""
    return Subquery(
        GameParticipation.objects.filter(filter_, session__status=COMPLETED)
        .values(group)
        .annotate(c=Count("id"))
        .order_by("-c", "session__game_id")
        .values("session__game_id")[:1]
    )


def registered_rows(search: str = "") -> QuerySet:
    me = Q(user=OuterRef("pk"))
    last_event = Subquery(
        ActivityEvent.objects.filter(me).order_by("-occurred_at").values("occurred_at")[:1]
    )
    last_game = Subquery(
        GameParticipation.objects.filter(me)
        .order_by("-session__ended_at")
        .values("session__ended_at")[:1]
    )
    users = User.objects.filter(profile__isnull=False)
    if search:
        users = users.filter(Q(username__icontains=search) | Q(profile__nickname__icontains=search))
    return users.annotate(
        row_key=Cast("pk", CharField()),
        row_kind=Value("registered", CharField()),
        row_user_id=F("pk"),
        row_username=F("username"),
        row_nickname=F("profile__nickname"),
        first_seen=F("date_joined"),
        last_seen=Greatest(
            Coalesce(last_event, F("date_joined")), Coalesce(last_game, F("date_joined"))
        ),
        games=Coalesce(_count(me & Q(session__status=COMPLETED)), 0),
        wins=Coalesce(_count(me & Q(is_win=True)), 0),
        win_rate=rate_expr(),
        favorite=_favorite(me, "user"),
    ).values(*ROW_FIELDS)


def guest_rows(search: str = "") -> QuerySet:
    parts = GameParticipation.objects.exclude(guest_key="")
    if search:
        matching = GameParticipation.objects.filter(nickname__icontains=search).exclude(
            guest_key=""
        )
        parts = parts.filter(guest_key__in=matching.values("guest_key"))
    me = Q(guest_key=OuterRef("guest_key"))
    latest_name = Subquery(
        GameParticipation.objects.filter(me).order_by("-session__started_at").values("nickname")[:1]
    )
    return (
        parts.values("guest_key")
        .annotate(
            row_key=F("guest_key"),
            row_kind=Value("guest", CharField()),
            row_user_id=Value(None, IntegerField()),
            row_username=Value("", CharField()),
            row_nickname=latest_name,
            first_seen=Min("session__started_at"),
            last_seen=Max("session__ended_at"),
            games=Count("id", filter=Q(session__status=COMPLETED)),
            wins=Count("id", filter=Q(is_win=True)),
            win_rate=rate_expr(),
            favorite=_favorite(me, "guest_key"),
        )
        .values(*ROW_FIELDS)
    )


def user_rows(search: str = "", kind: str = "", sort: str = DEFAULT_SORT, desc: bool = True):
    """The Users list as one sortable, sliceable queryset (registered ∪ guests)."""
    parts = []
    if kind in ("", "registered"):
        parts.append(registered_rows(search))
    if kind in ("", "guest"):
        parts.append(guest_rows(search))
    rows = parts[0] if len(parts) == 1 else parts[0].union(parts[1])
    column = F(SORTS.get(sort, DEFAULT_SORT))
    order = column.desc(nulls_last=True) if desc else column.asc(nulls_last=True)
    return rows.order_by(order, "row_key")


def decorate(row: dict[str, Any]) -> dict[str, Any]:
    """Display fields for a Users-list or leaderboard row."""
    games, wins = row.get("games") or 0, row.get("wins") or 0
    kind = row["row_kind"]
    return {
        **row,
        "losses": games - wins,
        "is_guest": kind == "guest",
        "short_key": row["row_key"][:8] if kind == "guest" else "",
        "favorite_name": game_name(row["favorite"]) if row.get("favorite") else None,
    }


# ----- user detail ---------------------------------------------------------------------


@dataclass(frozen=True)
class Actor:
    kind: str  # "registered" | "guest"
    user: User | None
    guest_key: str

    def q(self, prefix: str = "") -> Q:
        if self.user is not None:
            return Q(**{f"{prefix}user": self.user})
        return Q(**{f"{prefix}guest_key": self.guest_key})


def pick_most(per_game: list[dict[str, Any]], key: str, prefer_high_rate: bool):
    """Most-won (ties: higher win rate) or most-lost (ties: lower win rate) game, else None."""
    candidates = [g for g in per_game if g[key] > 0]
    if not candidates:
        return None

    def rank(g):
        rate = g["wins"] / g["played"] if g["played"] else 0
        return (-g[key], -rate if prefer_high_rate else rate, g["name"])

    return min(candidates, key=rank)


def actor_detail(actor: Actor) -> dict[str, Any]:
    parts = GameParticipation.objects.filter(actor.q())
    totals = parts.aggregate(
        games=Count("id", filter=Q(session__status=COMPLETED)),
        wins=Count("id", filter=Q(is_win=True)),
        abandoned=Count("id", filter=~Q(session__status=COMPLETED)),
        first=Min("session__started_at"),
        last=Max("session__ended_at"),
        nickname=Max("nickname"),
    )
    totals["losses"] = totals["games"] - totals["wins"]
    totals["win_rate"] = show_rate(totals["games"], totals["wins"])

    per_game = []
    for row in (
        parts.filter(session__status=COMPLETED)
        .values("session__game_id")
        .annotate(played=Count("id"), wins=Count("id", filter=Q(is_win=True)), avg=Avg("placement"))
        .order_by("session__game_id")
    ):
        per_game.append(
            {
                "id": row["session__game_id"],
                "name": game_name(row["session__game_id"]),
                "played": row["played"],
                "wins": row["wins"],
                "losses": row["played"] - row["wins"],
                "win_rate": show_rate(row["played"], row["wins"]),
                "avg_placement": row["avg"],
            }
        )
    per_game.sort(key=lambda g: (-g["played"], g["name"]))
    most_played = per_game[0] if per_game else None

    recent = list(
        parts.select_related("session")
        .prefetch_related(
            Prefetch(
                "session__participations",
                queryset=GameParticipation.objects.order_by("placement", "nickname"),
            )
        )
        .order_by("-session__started_at")[:20]
    )
    for part in recent:
        part.opponents = [o.nickname for o in part.session.participations.all() if o.pk != part.pk]

    mine = parts.filter(session__status=COMPLETED)
    my_place = Subquery(mine.filter(session=OuterRef("session")).values("placement")[:1])
    co_players = list(
        GameParticipation.objects.filter(KNOWN, session__in=mine.values("session"))
        .exclude(actor.q())
        .annotate(my_place=my_place)
        .values("user", "guest_key")
        .annotate(
            shared=Count("id"),
            ahead=Count("id", filter=Q(my_place__lt=F("placement"))),
            behind=Count("id", filter=Q(my_place__gt=F("placement"))),
            name=Max("nickname"),
        )
        .order_by("-shared", "name")[:10]
    )

    events = list(ActivityEvent.objects.filter(actor.q()).order_by("-occurred_at", "-id")[:50])
    return {
        "totals": totals,
        "per_game": per_game,
        "most_played": most_played,
        "most_won": pick_most(per_game, "wins", prefer_high_rate=True),
        "most_lost": pick_most(per_game, "losses", prefer_high_rate=False),
        "recent": recent,
        "co_players": co_players,
        "events": events,
    }


# ----- leaderboards --------------------------------------------------------------------


def leaderboards(game_id: str | None, limit: int = 10) -> dict[str, list[dict[str, Any]]]:
    base = GameParticipation.objects.filter(KNOWN, session__status=COMPLETED)
    if game_id:
        base = base.filter(session__game_id=game_id)
    grouped = base.values("user", "guest_key").annotate(
        games=Count("id"), wins=Count("id", filter=Q(is_win=True)), name=Max("nickname")
    )
    rated = grouped.annotate(win_rate=rate_expr()).filter(games__gte=DASHBOARD_MIN_GAMES_FOR_RATES)

    def rows(qs):
        return [
            {**r, "losses": r["games"] - r["wins"], "short_key": r["guest_key"][:8]}
            for r in qs[:limit]
        ]

    return {
        "most_wins": rows(grouped.filter(wins__gt=0).order_by("-wins", "-games", "name")),
        "best_rate": rows(rated.order_by("-win_rate", "-games", "name")),
        "most_games": rows(grouped.order_by("-games", "-wins", "name")),
    }
