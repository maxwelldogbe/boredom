"""Public tags, /api/auth/me additions, /api/me/stats and /api/me/recent-players."""

import importlib
import itertools
import json
import re
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from accounts import ratelimit, services, tags
from accounts.models import PlayerStats, Profile, TakenTag
from accounts.tokens import issue_token
from analytics.models import GameParticipation, GameSession
from games.constants import (
    DASHBOARD_MIN_GAMES_FOR_RATES,
    PLAYER_COLORS,
    RECENT_PLAYERS_DAYS,
    RECENT_PLAYERS_MAX,
    TAG_ALPHABET,
    TAG_LENGTH,
)
from rooms.models_types import Avatar
from tests.conftest import make_profile

pytestmark = pytest.mark.django_db

TAG_RE = re.compile(f"^[{TAG_ALPHABET}]{{{TAG_LENGTH}}}$")
backfill_module = importlib.import_module("accounts.migrations.0003_backfill_profile_tags")
_names = itertools.count(1)


@pytest.fixture(autouse=True)
def reset_limits() -> None:
    ratelimit.register_limiter.reset()
    ratelimit.login_limiter.reset()


def account(nickname: str = "Sam", username: str | None = None, stats=None) -> User:
    username = username or f"player_{next(_names)}"
    avatar = Avatar("cutouts", f"seed{next(_names)}")
    return services.create_account(
        username, "correct horse battery", nickname, PLAYER_COLORS[1], avatar, stats or {}
    )


def get(client: Client, path: str, user: User | None = None, token: str | None = None):
    token = token if token is not None else (issue_token(user.pk) if user else None)
    headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
    return client.get(path, **headers)


def session(players, *, days_ago: float = 1, status="completed", game_id="rps") -> GameSession:
    """A recorded session; `players` are Users or guest keys (str)."""
    ended = timezone.now() - timedelta(days=days_ago)
    s = GameSession.objects.create(
        game_id=game_id,
        room_code="ABCD",
        status=status,
        started_at=ended - timedelta(minutes=5),
        ended_at=ended,
        duration_seconds=300,
        player_count=len(players),
    )
    for i, p in enumerate(players):
        is_user = isinstance(p, User)
        GameParticipation.objects.create(
            session=s,
            user=p if is_user else None,
            guest_key="" if is_user else p,
            player_type="registered" if is_user else "guest",
            nickname=p.profile.nickname if is_user else "Guest",
            placement=i + 1 if status == "completed" else None,
            session_points=Decimal("0") if status == "completed" else None,
            is_win=i == 0 and status == "completed",
        )
    return s


# ----- tags ------------------------------------------------------------------------------------


def test_tag_format_and_uniqueness() -> None:
    users = [account() for _ in range(40)]
    found = [u.profile.tag for u in users]
    assert all(TAG_RE.fullmatch(t) for t in found)
    assert len(set(found)) == 40
    assert set(TakenTag.objects.values_list("tag", flat=True)) >= set(found)


def test_tag_never_contains_the_username(monkeypatch) -> None:
    draws = iter(["ABCXYZ", "QQQQQQ"])  # the first draw contains "ABC"
    monkeypatch.setattr(tags, "random_tag", lambda: next(draws))
    user = account(username="abc")
    assert user.profile.tag == "QQQQQQ"
    assert not tags.reveals(user.profile.tag, "abc")
    monkeypatch.undo()
    for u in [account(username=f"user_{i}") for i in range(10)]:
        assert u.username.upper() not in u.profile.tag


def test_tag_is_stable_across_nickname_changes(client: Client) -> None:
    user = account()
    before = user.profile.tag
    token = issue_token(user.pk)
    response = client.patch(
        "/api/auth/profile",
        data=json.dumps({"nickname": "Renamed", "color": PLAYER_COLORS[3]}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert response.status_code == 200
    assert Profile.objects.get(user=user).tag == before
    assert get(client, "/api/auth/me", user).json()["tag"] == before


def test_deleted_accounts_tags_are_never_reused(monkeypatch) -> None:
    user = account()
    old = user.profile.tag
    services.delete_account(user)
    assert TakenTag.objects.filter(tag=old).exists()
    draws = iter([old, "ZZZZZZ"])  # the next account first draws the deleted one's tag
    monkeypatch.setattr(tags, "random_tag", lambda: next(draws))
    assert account().profile.tag == "ZZZZZZ"


def test_collisions_are_retried(monkeypatch) -> None:
    first = account()
    draws = iter([first.profile.tag, "YYYYYY"])
    monkeypatch.setattr(tags, "random_tag", lambda: next(draws))
    assert account().profile.tag == "YYYYYY"


def test_backfill_tags_existing_accounts_and_is_idempotent(monkeypatch) -> None:
    users = [account() for _ in range(5)]
    kept = users[0].profile.tag
    Profile.objects.filter(user__in=users[1:]).update(tag=None)
    TakenTag.objects.all().delete()  # as before the migration: no tags recorded yet
    backfill_module.backfill(apps, None)
    tagged = dict(Profile.objects.values_list("user_id", "tag"))
    assert tagged[users[0].pk] == kept
    assert all(TAG_RE.fullmatch(tagged[u.pk]) for u in users)
    assert len({tagged[u.pk] for u in users}) == 5
    assert set(TakenTag.objects.values_list("tag", flat=True)) == {tagged[u.pk] for u in users}
    backfill_module.backfill(apps, None)  # running it again changes nothing
    assert dict(Profile.objects.values_list("user_id", "tag")) == tagged
    assert TakenTag.objects.count() == 5


def test_backfill_retries_collisions(monkeypatch) -> None:
    a, b = account(), account()
    Profile.objects.filter(user=b).update(tag=None)
    draws = iter(a.profile.tag + "WWWWWW")
    monkeypatch.setattr(backfill_module.secrets, "choice", lambda alphabet: next(draws))
    backfill_module.backfill(apps, None)
    assert Profile.objects.get(user=b).tag == "WWWWWW"


async def test_tag_is_not_in_room_state(connect) -> None:
    from asgiref.sync import sync_to_async

    user = await sync_to_async(account)()
    tag = user.profile.tag
    client = await connect()
    ack = await client.request(
        "room:create", {"profile": make_profile("Sam"), "authToken": issue_token(user.pk)}
    )
    assert ack["ok"]
    await client.drain()
    everything = json.dumps([ack, *client.pushes])
    assert tag not in everything and "tag" not in ack["data"]["room"]["players"][0]


# ----- /api/auth/me ----------------------------------------------------------------------------


def test_me_adds_tag_and_iso_created_at_and_keeps_the_rest(client: Client) -> None:
    user = account()
    data = get(client, "/api/auth/me", user).json()
    assert set(data) == {"profile", "stats", "tag", "createdAt"}
    assert data["tag"] == user.profile.tag
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", data["createdAt"])
    assert set(data["profile"]) == {
        "username",
        "nickname",
        "color",
        "avatar",
        "type",
        "createdAt",
        "avatarLockedUntil",
    }
    assert isinstance(data["profile"]["createdAt"], int)  # unchanged: epoch ms


# ----- auth and caching ------------------------------------------------------------------------

PATHS = ["/api/auth/me", "/api/me/stats", "/api/me/recent-players"]


@pytest.mark.parametrize("path", PATHS)
def test_endpoints_need_a_token_and_never_cache(client: Client, path: str) -> None:
    for token in ("", "not-a-token"):
        response = get(client, path, token=token)
        assert response.status_code == 401
        assert response.json() == {
            "error": {"code": "UNAUTHORIZED", "message": "Please log in again."}
        }
        assert response["Cache-Control"] == "no-store"
    disabled = account()
    User.objects.filter(pk=disabled.pk).update(is_active=False)
    assert get(client, path, disabled).status_code == 401
    ok = get(client, path, account())
    assert ok.status_code == 200 and ok["Cache-Control"] == "no-store"


# ----- /api/me/stats ---------------------------------------------------------------------------


def stats_of(client: Client, user: User) -> dict[str, Any]:
    return get(client, "/api/me/stats", user).json()


def test_stats_empty(client: Client) -> None:
    assert stats_of(client, account()) == {
        "totals": {"played": 0, "wins": 0, "losses": 0, "winRate": None},
        "favoriteGame": None,
        "perGame": [],
        "minGamesForRate": DASHBOARD_MIN_GAMES_FOR_RATES,
    }


def test_stats_math_and_rate_threshold(client: Client) -> None:
    n = DASHBOARD_MIN_GAMES_FOR_RATES
    user = account(stats={"rps": (n, 2), "hangman": (n - 1, n - 1)})
    data = stats_of(client, user)
    assert data["totals"] == {
        "played": 2 * n - 1,
        "wins": n + 1,
        "losses": n - 2,
        "winRate": round((n + 1) / (2 * n - 1), 4),
    }
    assert data["perGame"] == [
        {"gameId": "rps", "played": n, "wins": 2, "losses": n - 2, "winRate": round(2 / n, 4)},
        {"gameId": "hangman", "played": n - 1, "wins": n - 1, "losses": 0, "winRate": None},
    ]
    assert data["favoriteGame"] == "rps"


def test_total_rate_is_null_below_the_threshold(client: Client) -> None:
    user = account(stats={"rps": (DASHBOARD_MIN_GAMES_FOR_RATES - 1, 1)})
    assert stats_of(client, user)["totals"]["winRate"] is None


def test_favorite_game_tie_breaks(client: Client) -> None:
    # Same played: more wins wins. Same played and wins: alphabetical by game id.
    assert stats_of(client, account(stats={"rps": (4, 1), "hangman": (4, 3)}))["favoriteGame"] == (
        "hangman"
    )
    tied = account(stats={"rps": (4, 2), "liars_dice": (4, 2), "hangman": (4, 2)})
    data = stats_of(client, tied)
    assert data["favoriteGame"] == "hangman"
    assert [g["gameId"] for g in data["perGame"]] == ["hangman", "liars_dice", "rps"]


def test_games_never_played_have_no_row(client: Client) -> None:
    user = account(stats={"rps": (3, 1)})
    PlayerStats.objects.create(user=user, game_id="hangman", played=0, wins=0)
    assert [g["gameId"] for g in stats_of(client, user)["perGame"]] == ["rps"]


# ----- /api/me/recent-players ------------------------------------------------------------------


def recent(client: Client, user: User) -> list[dict[str, Any]]:
    return get(client, "/api/me/recent-players", user).json()["players"]


def test_recent_players_shape_and_counts(client: Client) -> None:
    me, ann, bob = account("Me"), account("Ann"), account("Bob")
    session([me, ann], days_ago=3, game_id="rps")
    session([me, ann, bob], days_ago=2, game_id="hangman")
    session([me, ann], days_ago=1, game_id="liars_dice")
    players = recent(client, me)
    assert [p["nickname"] for p in players] == ["Ann", "Bob"]  # newest first, each once
    first = players[0]
    assert set(first) == {
        "tag",
        "nickname",
        "avatar",
        "color",
        "lastPlayedAt",
        "gamesTogether",
        "lastGameId",
        "relationship",
    }
    assert first["tag"] == ann.profile.tag and first["gamesTogether"] == 3
    assert first["lastGameId"] == "liars_dice"
    assert first["avatar"] == {"style": ann.profile.avatar_style, "seed": ann.profile.avatar_seed}
    assert first["color"] == ann.profile.color
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", first["lastPlayedAt"])
    assert players[1]["gamesTogether"] == 1 and players[1]["lastGameId"] == "hangman"


def test_recent_players_exclusions(client: Client) -> None:
    me, ann = account("Me"), account("Ann")
    disabled, deleted, old, abandoned = (
        account("Dis"),
        account("Del"),
        account("Old"),
        account("Ab"),
    )
    session([me, ann, "guest-key-1", disabled, deleted], days_ago=1)
    session([me, old], days_ago=RECENT_PLAYERS_DAYS + 1)
    session([me, abandoned], days_ago=1, status="abandoned")
    session([ann, account("Stranger")], days_ago=1)  # not with me
    User.objects.filter(pk=disabled.pk).update(is_active=False)
    services.delete_account(deleted)
    assert [p["nickname"] for p in recent(client, me)] == ["Ann"]


def test_games_together_only_counts_the_window(client: Client) -> None:
    me, ann = account("Me"), account("Ann")
    session([me, ann], days_ago=RECENT_PLAYERS_DAYS + 2)
    session([me, ann], days_ago=2)
    session([me, ann], days_ago=1, status="abandoned")
    assert recent(client, me)[0]["gamesTogether"] == 1


def test_recent_players_are_capped(client: Client) -> None:
    me = account("Me")
    others = [account(f"P{i}") for i in range(RECENT_PLAYERS_MAX + 3)]
    for i, other in enumerate(others):
        session([me, other], days_ago=1 + i / 100)  # others[0] is the newest
    players = recent(client, me)
    assert len(players) == RECENT_PLAYERS_MAX
    assert (
        players[0]["nickname"] == "P0" and players[-1]["nickname"] == f"P{RECENT_PLAYERS_MAX - 1}"
    )


def test_no_ids_usernames_or_guest_keys_in_any_payload(client: Client) -> None:
    me, ann = account("Me", username="secret_me"), account("Ann", username="secret_ann")
    session([me, ann, "guest-key-xyz"], days_ago=1)
    for path in ("/api/me/stats", "/api/me/recent-players"):
        text = get(client, path, me).text
        for secret in (
            "secret_me",
            "secret_ann",
            "guest-key-xyz",
            f'"{ann.pk}"',
            "userId",
            "user_id",
        ):
            assert secret not in text, (path, secret)
    players = recent(client, me)
    assert not ({"id", "userId", "username", "profileId", "email", "guestKey"} & set(players[0]))
    me_text = get(client, "/api/auth/me", me).text
    assert "secret_ann" not in me_text and "guest-key-xyz" not in me_text
