"""The account holder's own stats and recent players, computed on the server.

Nothing here returns a login username, user id, profile id, email or guest key.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from django.contrib.auth.models import User
from django.utils import timezone

from accounts.models import Profile
from accounts.tags import ensure_tag
from analytics.models import GameParticipation, GameSession
from games.constants import DASHBOARD_MIN_GAMES_FOR_RATES, RECENT_PLAYERS_DAYS, RECENT_PLAYERS_MAX


def iso(moment: datetime) -> str:
    """ISO-8601 in UTC with a Z, e.g. 2026-10-27T11:31:05Z."""
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def win_rate(played: int, wins: int) -> float | None:
    """wins / played, once there are DASHBOARD_MIN_GAMES_FOR_RATES games (as the dashboard)."""
    return round(wins / played, 4) if played >= DASHBOARD_MIN_GAMES_FOR_RATES else None


def stats(user: User) -> dict[str, Any]:
    """Totals, favorite game and per-game rows from the PlayerStats counters.

    Ties count as wins already (placement 1), so losses = played - wins. Per-game rows are
    ordered like the favorite: most played, then most wins, then game id.
    """
    rows = sorted(
        ((s.game_id, s.played, s.wins) for s in user.stats.all() if s.played > 0),
        key=lambda r: (-r[1], -r[2], r[0]),
    )
    played = sum(r[1] for r in rows)
    wins = sum(r[2] for r in rows)
    return {
        "totals": {
            "played": played,
            "wins": wins,
            "losses": played - wins,
            "winRate": win_rate(played, wins),
        },
        "favoriteGame": rows[0][0] if rows else None,
        "perGame": [
            {"gameId": g, "played": p, "wins": w, "losses": p - w, "winRate": win_rate(p, w)}
            for g, p, w in rows
        ],
        "minGamesForRate": DASHBOARD_MIN_GAMES_FOR_RATES,
    }


def recent_players(user: User, now: datetime | None = None) -> list[dict[str, Any]]:
    """Registered players who shared a completed session with `user` in the window, newest first.

    Guests, the requester, disabled accounts and deleted accounts (whose rows have no user)
    are left out. gamesTogether counts shared completed sessions within the window.
    """
    since = (now or timezone.now()) - timedelta(days=RECENT_PLAYERS_DAYS)
    mine = GameSession.objects.filter(
        status=GameSession.Status.COMPLETED, ended_at__gte=since, participations__user=user
    )
    shared = (
        GameParticipation.objects.filter(session__in=mine, user__isnull=False, user__is_active=True)
        .exclude(user=user)
        .values_list("user_id", "session_id", "session__ended_at", "session__game_id")
    )
    together: dict[int, dict[str, Any]] = {}
    for user_id, session_id, ended_at, game_id in shared:
        entry = together.setdefault(user_id, {"sessions": set(), "last": ended_at, "game": game_id})
        entry["sessions"].add(session_id)
        if ended_at > entry["last"]:
            entry["last"], entry["game"] = ended_at, game_id
    newest = sorted(together.items(), key=lambda kv: (kv[1]["last"], kv[0]), reverse=True)
    newest = newest[:RECENT_PLAYERS_MAX]
    profiles = Profile.objects.filter(user_id__in=[uid for uid, _ in newest]).select_related("user")
    by_user = {p.user_id: p for p in profiles}
    out = []
    for user_id, entry in newest:
        profile = by_user.get(user_id)
        if profile is None:
            continue  # an account without a saved profile is not a player
        out.append(
            {
                "tag": ensure_tag(profile),
                "nickname": profile.nickname,
                "avatar": {"style": profile.avatar_style, "seed": profile.avatar_seed},
                "color": profile.color,
                "lastPlayedAt": iso(entry["last"]),
                "gamesTogether": len(entry["sessions"]),
                "lastGameId": entry["game"],
            }
        )
    return out
