"""Staff JSON API for the React dashboard: access, CSRF, shapes, actions, no secrets."""

import json

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.core.cache import cache
from django.test import Client

from accounts.tokens import issue_token
from analytics.models import DELETED_NICKNAME, GameParticipation
from tests.dashboard_data import GUEST_CARL, PASSWORD, account, play

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("fresh_state")]

A = "/api/admin/"
READS = [
    "overview",
    "overview?range=all",
    "games",
    "games/rps",
    "users",
    "users?type=guest&sort=win_rate&dir=asc&q=c",
    "leaderboards",
    "leaderboards?game=hangman",
    "activity",
    "activity?kind=login",
]


def staff(superuser: bool = True, csrf: bool = False) -> Client:
    maker = User.objects.create_superuser if superuser else User.objects.create_user
    boss = maker(username="boss", password=PASSWORD, **({} if superuser else {"is_staff": True}))
    client = Client(HTTP_HOST="localhost", enforce_csrf_checks=csrf)
    client.force_login(boss)
    return client


def get(client: Client, path: str) -> dict:
    response = client.get(A + path)
    assert response.status_code == 200, (path, response.content[:300])
    assert response["Content-Type"] == "application/json"
    return response.json()


# ----- session and access ------------------------------------------------------------


def test_session_for_anonymous_gives_login_url_and_csrf() -> None:
    client = Client(HTTP_HOST="localhost")
    data = get(client, "session")
    assert data["staff"] is False and data["username"] is None
    assert data["loginUrl"] == "/manage/login/"
    assert data["logoutUrl"] == "/manage/logout/"
    assert data["exports"] == {
        "users": "/manage/dashboard/export/users.csv",
        "sessions": "/manage/dashboard/export/sessions.csv",
    }
    assert data["csrfToken"] and "csrftoken" in client.cookies
    assert data["minGamesForRates"] == 5


def test_session_for_staff() -> None:
    data = get(staff(), "session")
    assert data["staff"] is True and data["username"] == "boss" and data["superuser"] is True


def test_session_for_a_player_is_not_staff() -> None:
    client = Client(HTTP_HOST="localhost")
    client.force_login(account("player", "Player"))
    assert get(client, "session")["staff"] is False


def test_reads_require_staff(world) -> None:
    anonymous = Client(HTTP_HOST="localhost")
    player = Client(HTTP_HOST="localhost")
    player.force_login(account("player", "Player"))
    paths = READS + [f"users/u/{world['alice'].pk}", f"users/g/{GUEST_CARL}"]
    for path in paths:
        denied = anonymous.get(A + path)
        assert denied.status_code == 401, path
        assert denied.json()["error"] == {
            "code": "UNAUTHORIZED",
            "message": "Log in as staff.",
            "loginUrl": "/manage/login/",
        }
        assert player.get(A + path).status_code == 403, path


def test_staff_can_read_everything(world) -> None:
    client = staff(superuser=False)
    for path in READS + [f"users/u/{world['alice'].pk}", f"users/g/{GUEST_CARL}"]:
        get(client, path)


def test_every_read_works_on_an_empty_database() -> None:
    client = staff()
    for path in READS:
        get(client, path)


def test_unknown_things_are_404() -> None:
    client = staff()
    for path in ["games/chess", "users/u/999", f"users/g/{'e' * 16}"]:
        response = client.get(A + path)
        assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"


# ----- shapes ------------------------------------------------------------------------


def test_overview_shape(world) -> None:
    data = get(staff(), "overview?range=all")
    assert data["range"] == {"key": "all", "label": "All time"}
    assert [r["key"] for r in data["ranges"]] == ["today", "7d", "30d", "all"]
    assert data["sessions"]["completed"] == 9 and data["sessions"]["abandoned"] == 1
    assert data["sessions"]["abandonRate"] == pytest.approx(0.1)
    assert data["mostPlayed"] == {"id": "rps", "name": "Rock-Paper-Scissors", "plays": 6}
    assert data["users"] == {"total": 2, "new": 2}
    assert data["active"] == {"daily": 2, "weekly": 3, "monthly": 3}
    assert len(data["perDay"]) == 30 and set(data["perDay"][0]) == {"date", "count"}
    assert data["perDay"][0]["date"].count("-") == 2
    assert data["live"] == []


def test_games_and_game_detail_shape(world) -> None:
    client = staff()
    rows = {g["id"]: g for g in get(client, "games?range=all")["games"]}
    assert rows["rps"]["plays"] == 6 and rows["rps"]["uniquePlayers"] == 2
    assert rows["rps"]["completionRate"] == pytest.approx(6 / 7)
    detail = get(client, "games/rps?range=all")
    assert detail["game"] == {"id": "rps", "name": "Rock-Paper-Scissors"}
    assert detail["totals"]["plays"] == 6 and len(detail["perDay"]) == 30
    assert len(detail["recent"]) == 7 and "startedAt" in detail["recent"][0]


def test_users_shape_and_paging(world, monkeypatch) -> None:
    from analytics import api

    monkeypatch.setattr(api, "DASHBOARD_PAGE_SIZE", 2)
    client = staff()
    first = get(client, "users?sort=games")
    assert (first["page"], first["numPages"], first["count"]) == (1, 2, 4)
    alice = first["results"][0]
    assert (
        alice["kind"] == "registered" and alice["name"] == "Alice" and alice["username"] == "alice"
    )
    assert (alice["games"], alice["wins"], alice["losses"]) == (9, 5, 4)
    assert alice["winRate"] == pytest.approx(5 / 9)
    assert alice["favorite"] == {"id": "rps", "name": "Rock-Paper-Scissors"}
    carl = first["results"][1]
    assert (
        carl["kind"] == "guest" and carl["guestKey"] == GUEST_CARL and carl["shortKey"] == "c" * 8
    )
    assert carl["username"] is None
    second = get(client, "users?sort=games&page=2")
    bob = second["results"][0]
    assert bob["name"] == "Bob" and bob["winRate"] is None  # below 5 games
    assert get(client, "users?q=zzz")["results"] == []


def test_user_detail_shape(world) -> None:
    alice = world["alice"]
    data = get(staff(), f"users/u/{alice.pk}")
    assert data["actor"]["name"] == "Alice" and data["actor"]["username"] == "alice"
    assert data["actor"]["isActive"] is True
    assert data["permissions"] == {"change": True, "delete": True}
    assert data["totals"]["games"] == 9 and data["totals"]["winRate"] == pytest.approx(5 / 9)
    assert data["mostPlayed"]["id"] == "rps" and data["mostLost"]["id"] == "hangman"
    assert len(data["recent"]) == 10
    co = {c["name"]: c for c in data["coPlayers"]}
    assert co["Carl"]["kind"] == "guest" and co["Carl"]["guestKey"] == GUEST_CARL
    assert (co["Carl"]["ahead"], co["Carl"]["behind"]) == (4, 2)
    assert co["Bob"]["kind"] == "registered" and co["Bob"]["userId"] == world["bob"].pk
    assert [e["kind"] for e in data["events"]] == ["login"]


def test_guest_detail_shape(world) -> None:
    data = get(staff(), f"users/g/{GUEST_CARL}")
    assert data["actor"]["kind"] == "guest" and data["actor"]["name"] == "Carl"
    assert data["actor"]["username"] is None
    assert data["permissions"] == {"change": False, "delete": False}
    assert data["totals"]["games"] == 6


def test_leaderboards_and_activity_shape(world) -> None:
    client = staff()
    boards = get(client, "leaderboards")
    assert [r["name"] for r in boards["mostWins"]] == ["Alice", "Bob", "Carl"]
    assert [r["name"] for r in boards["bestRate"]] == ["Alice", "Carl"]
    assert (
        boards["game"] is None and {"id": "rps", "name": "Rock-Paper-Scissors"} in boards["games"]
    )
    assert get(client, "leaderboards?game=hangman")["game"]["id"] == "hangman"
    feed = get(client, "activity")
    assert feed["count"] == 3
    assert feed["results"][0]["kind"] in {"login", "room_joined"}
    assert {"value": "login", "label": "Login"} in feed["kinds"]
    logins = get(client, "activity?kind=login")["results"]
    assert len(logins) == 1 and logins[0]["who"]["name"] == "Alice"


# ----- actions -----------------------------------------------------------------------


def _csrf(client: Client) -> str:
    return client.get(A + "session").json()["csrfToken"]


def test_actions_need_post_and_csrf(world) -> None:
    client = staff(csrf=True)
    alice = world["alice"]
    url = A + f"users/u/{alice.pk}/disable"
    assert client.get(url).status_code == 405
    assert client.post(url).status_code == 403  # no CSRF token
    assert User.objects.get(pk=alice.pk).is_active
    response = client.post(url, HTTP_X_CSRFTOKEN=_csrf(client))
    assert response.status_code == 200 and response.json() == {"ok": True, "isActive": False}
    assert not User.objects.get(pk=alice.pk).is_active
    enable = client.post(A + f"users/u/{alice.pk}/enable", HTTP_X_CSRFTOKEN=_csrf(client))
    assert enable.json()["isActive"] is True
    messages = LogEntry.objects.order_by("id").values_list("change_message", flat=True)
    assert list(messages) == ["Disabled account", "Enabled account"]


def test_disabled_account_loses_its_game_login(world) -> None:
    client = staff(csrf=True)
    alice = world["alice"]
    token = issue_token(alice.pk)
    client.post(A + f"users/u/{alice.pk}/disable", HTTP_X_CSRFTOKEN=_csrf(client))
    me = Client(HTTP_HOST="localhost").get("/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert me.status_code == 401


def test_delete_action_anonymises(world) -> None:
    client = staff(csrf=True)
    bob = world["bob"]
    response = client.post(A + f"users/u/{bob.pk}/delete", HTTP_X_CSRFTOKEN=_csrf(client))
    assert response.json() == {"ok": True, "deleted": True}
    assert not User.objects.filter(pk=bob.pk).exists()
    assert GameParticipation.objects.filter(nickname=DELETED_NICKNAME).count() == 3
    assert LogEntry.objects.filter(object_repr="bob", action_flag=3).exists()


def test_staff_without_permissions_cannot_act(world) -> None:
    client = staff(superuser=False)
    alice = world["alice"]
    for action in ("disable", "delete"):
        response = client.post(A + f"users/u/{alice.pk}/{action}")
        assert response.status_code == 403
    assert User.objects.get(pk=alice.pk).is_active
    boss = User.objects.get(username="boss")
    boss.user_permissions.add(Permission.objects.get(codename="change_user"))
    client.force_login(User.objects.get(pk=boss.pk))
    assert client.post(A + f"users/u/{alice.pk}/disable").status_code == 200
    assert client.post(A + f"users/u/{alice.pk}/delete").status_code == 403


def test_unknown_action_or_account(world) -> None:
    client = staff()
    assert client.post(A + f"users/u/{world['alice'].pk}/promote").status_code == 404
    assert client.post(A + "users/u/999/disable").status_code == 404


# ----- secrets and cost --------------------------------------------------------------


def test_no_secrets_in_any_response(world) -> None:
    client = staff()
    alice = world["alice"]
    token = issue_token(alice.pk)
    text = "".join(
        json.dumps(get(client, path))
        for path in READS + ["session", f"users/u/{alice.pk}", f"users/g/{GUEST_CARL}"]
    )
    assert alice.password not in text and "md5$" not in text and "pbkdf2" not in text
    assert token not in text and "127.0.0.1" not in text
    assert "roomToken" not in text and "profileId" not in text


def test_read_queries_do_not_grow_with_data(world) -> None:
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client = staff()
    alice = world["alice"]
    paths = ["overview", "games", "users", f"users/u/{alice.pk}", "leaderboards", "activity"]

    def counts() -> dict[str, int]:
        out = {}
        for path in paths:
            cache.clear()
            with CaptureQueriesContext(connection) as ctx:
                get(client, path)
            out[path] = len(ctx.captured_queries)
        return out

    before = counts()
    for i in range(12):
        extra = account(f"extra{i}", f"Extra{i}")
        play("rps", [(alice, "Alice", 1), (f"{i:016x}", f"G{i}", 2), (extra, f"Extra{i}", 3)])
    assert counts() == before
