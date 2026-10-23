"""Admin dashboard: access, lockout, read-only models, every page, metrics, CSV, actions."""

import csv
import io
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from accounts.models import PlayerStats
from accounts.tokens import issue_token
from analytics import metrics, people
from analytics.models import DELETED_NICKNAME, ActivityEvent, GameParticipation, GameSession
from games.constants import ADMIN_LOGIN_MAX_FAILS, PLAYER_COLORS
from rooms import manager as manager_module
from rooms.manager import RoomManager
from rooms.models_types import Avatar, Player, Room
from tests.dashboard_data import GUEST_CARL, PASSWORD, account, play

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("fresh_state")]

CORE = Path(__file__).resolve().parents[1]
M = "/manage/"
PAGES = [
    "",
    "dashboard/games/",
    "dashboard/games/rps/",
    "dashboard/users/",
    "dashboard/leaderboards/",
    "dashboard/leaderboards/?game=rps",
    "dashboard/activity/",
    "dashboard/data/",
]


def staff_client(superuser: bool = True) -> Client:
    maker = User.objects.create_superuser if superuser else User.objects.create_user
    boss = maker(username="boss", password=PASSWORD, **({} if superuser else {"is_staff": True}))
    client = Client(HTTP_HOST="localhost")
    client.force_login(boss)
    return client


# ----- access control and security ---------------------------------------------------


def test_anonymous_is_sent_to_login() -> None:
    client = Client(HTTP_HOST="localhost")
    for page in PAGES + ["dashboard/export/users.csv"]:
        response = client.get(M + page)
        assert response.status_code == 302, page
        assert response["Location"].startswith(M + "login/"), page


def test_non_staff_players_are_blocked() -> None:
    player = account("player", "Player")
    client = Client(HTTP_HOST="localhost")
    client.force_login(player)
    for page in PAGES + ["dashboard/export/sessions.csv"]:
        assert client.get(M + page).status_code == 302, page
    # and they cannot log in to the admin either
    client.logout()
    response = client.post(M + "login/", {"username": "player", "password": PASSWORD})
    assert response.status_code == 200 and "_auth_user_id" not in client.session


def test_game_signup_never_creates_staff() -> None:
    client = Client(HTTP_HOST="localhost")
    body = json.dumps(
        {
            "username": "sneaky",
            "password": PASSWORD,
            "profile": {"nickname": "S", "color": PLAYER_COLORS[0]},
            "is_staff": True,
            "is_superuser": True,
        }
    )
    assert (
        client.post("/api/auth/register", body, content_type="application/json").status_code == 201
    )
    user = User.objects.get(username="sneaky")
    assert not user.is_staff and not user.is_superuser


def test_staff_without_superuser_can_view_pages(world) -> None:
    client = staff_client(superuser=False)
    for page in PAGES:
        assert client.get(M + page).status_code == 200, page


def test_admin_responses_are_noindex() -> None:
    client = staff_client()
    response = client.get(M)
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    assert b'<meta name="robots" content="noindex, nofollow">' in response.content
    login = Client(HTTP_HOST="localhost").get(M + "login/")
    assert login["X-Robots-Tag"] == "noindex, nofollow"
    assert "X-Robots-Tag" not in Client(HTTP_HOST="localhost").get("/api/health")


def test_admin_login_lockout() -> None:
    User.objects.create_superuser(username="boss", password=PASSWORD)
    client = Client(HTTP_HOST="localhost")
    for _ in range(ADMIN_LOGIN_MAX_FAILS):
        response = client.post(M + "login/", {"username": "boss", "password": "wrong-guess"})
        assert response.status_code == 200
    locked = client.post(M + "login/", {"username": "Boss", "password": PASSWORD})
    assert locked.status_code == 429
    assert b"Too many failed" in locked.content
    assert "_auth_user_id" not in client.session
    # another username from the same IP is not locked
    other = client.post(M + "login/", {"username": "someone", "password": "x"})
    assert other.status_code == 200


def test_admin_lockout_expires_and_success_resets() -> None:
    now = [0.0]
    from analytics.lockout import LoginLockout

    lock = LoginLockout(max_fails=2, lock_seconds=60, clock=lambda: now[0])
    key = lock.key("1.2.3.4", "Boss")
    lock.failed(key)
    lock.failed(key)
    assert lock.locked(lock.key("1.2.3.4", "boss"))
    now[0] = 61
    assert not lock.locked(key)
    lock.failed(key)
    lock.succeeded(key)
    lock.failed(key)
    assert not lock.locked(key)


def test_good_admin_login_works() -> None:
    User.objects.create_superuser(username="boss", password=PASSWORD)
    client = Client(HTTP_HOST="localhost")
    response = client.post(M + "login/", {"username": "boss", "password": PASSWORD})
    assert response.status_code == 302
    assert client.get(M).status_code == 200


def test_production_settings_secure_cookies_and_whitenoise() -> None:
    code = (
        "import django, os; django.setup(); from django.conf import settings as s; "
        "print(s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_PROXY_SSL_HEADER, "
        "'whitenoise.middleware.WhiteNoiseMiddleware' in s.MIDDLEWARE, s.ADMIN_URL_PREFIX, "
        "s.TIME_ZONE, s.CSRF_TRUSTED_ORIGINS)"
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DJANGO_DEBUG": "false",
        "DJANGO_SECRET_KEY": "x" * 50,
        "ADMIN_URL_PREFIX": "/secret-door",
        "TIME_ZONE": "Africa/Accra",
        "CSRF_TRUSTED_ORIGINS": "https://api.example.com",
    }
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=CORE, env=env, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out == (
        "True True ('HTTP_X_FORWARDED_PROTO', 'https') True secret-door/ Africa/Accra "
        "['https://api.example.com']"
    )


# ----- read-only analytics models ----------------------------------------------------


def test_analytics_models_are_read_only(world) -> None:
    client = staff_client()
    session = GameSession.objects.first()
    for model in ["gamesession", "gameparticipation", "activityevent"]:
        assert client.get(f"{M}analytics/{model}/").status_code == 200
        assert client.get(f"{M}analytics/{model}/add/").status_code == 403
    change = client.get(f"{M}analytics/gamesession/{session.pk}/change/")
    assert change.status_code == 200 and b'name="_save"' not in change.content
    posted = client.post(f"{M}analytics/gamesession/{session.pk}/change/", {"game_id": "hacked"})
    assert posted.status_code == 403
    assert GameSession.objects.get(pk=session.pk).game_id != "hacked"


def test_only_superusers_delete_analytics_rows(world) -> None:
    session = GameSession.objects.first()
    staff = staff_client(superuser=False)
    url = f"{M}analytics/gamesession/{session.pk}/delete/"
    assert staff.get(url).status_code == 403
    User.objects.filter(username="boss").delete()
    boss = staff_client()
    assert boss.get(url).status_code == 200


# ----- pages render ------------------------------------------------------------------


def test_every_page_renders_with_an_empty_database() -> None:
    client = staff_client()
    for page in PAGES:
        for rng in ("today", "7d", "30d", "all", "bogus"):
            sep = "&" if "?" in page else "?"
            assert client.get(f"{M}{page}{sep}range={rng}").status_code == 200, page


def test_every_page_renders_with_data(world) -> None:
    client = staff_client()
    alice = world["alice"]
    for page in PAGES + [
        f"dashboard/users/u/{alice.pk}/",
        f"dashboard/users/g/{GUEST_CARL}/",
        "dashboard/users/?type=guest&sort=win_rate&dir=asc",
        "dashboard/users/?q=ali",
        "dashboard/activity/?kind=login",
        f"dashboard/activity/?date={timezone.localdate():%Y-%m-%d}",
        "dashboard/games/hangman/?range=all",
    ]:
        assert client.get(M + page).status_code == 200, page


def test_unknown_game_or_guest_is_404() -> None:
    client = staff_client()
    assert client.get(M + "dashboard/games/chess/").status_code == 404
    assert client.get(M + f"dashboard/users/g/{'e' * 16}/").status_code == 404
    assert client.get(M + "dashboard/users/u/999/").status_code == 404


# ----- metrics -----------------------------------------------------------------------


def test_overview_numbers(world) -> None:
    data = metrics.overview(metrics.parse_range("all"))
    s = data["sessions"]
    assert s["completed"] == 9 and s["abandoned"] == 1
    assert s["abandon_rate"] == pytest.approx(0.1)
    assert s["avg_players"] == 2
    assert s["avg_duration"] == pytest.approx((6 * 60 + 3 * 120) / 9)
    assert data["most_played"]["id"] == "rps" and data["most_played"]["plays"] == 6
    assert data["users"] == {"total": 2, "new": 2}
    assert data["guests_seen"] == 2  # Carl and Dana (one key may appear in both sources)
    assert data["active"] == {"daily": 2, "weekly": 3, "monthly": 3}
    assert sum(n for _, n in data["per_day"]) == 9


def test_overview_range_filters(world) -> None:
    week = metrics.overview(metrics.parse_range("7d"))
    assert week["sessions"]["completed"] == 9
    GameSession.objects.filter(game_id="hangman").update(
        started_at=timezone.now() - timedelta(days=40)
    )
    month = metrics.overview(metrics.parse_range("30d"))
    assert month["sessions"]["completed"] == 6
    assert metrics.overview(metrics.parse_range("all"))["sessions"]["completed"] == 9


def test_overview_is_cached_for_a_minute(world, django_assert_num_queries) -> None:
    client = staff_client()
    assert b">9<" in client.get(M + "?range=all").content
    play("rps", [(GUEST_CARL, "Carl", 1)])
    assert b">9<" in client.get(M + "?range=all").content  # cached
    cache.clear()
    assert b">10<" in client.get(M + "?range=all").content


def test_games_table(world) -> None:
    rows = {r["id"]: r for r in metrics.games_table(metrics.parse_range("all"))}
    assert rows["rps"]["plays"] == 6 and rows["rps"]["abandoned"] == 1
    assert rows["rps"]["unique_players"] == 2  # Alice + Carl (Dana only abandoned)
    assert rows["rps"]["completion_rate"] == pytest.approx(6 / 7)
    assert rows["hangman"]["plays"] == 3 and rows["hangman"]["unique_players"] == 2
    assert rows["hangman"]["avg_duration"] == 120
    assert rows["liars_dice"]["plays"] == 0 and rows["liars_dice"]["completion_rate"] is None


def test_game_detail_bars(world) -> None:
    detail = metrics.game_detail("rps", metrics.parse_range("all"))
    assert len(detail["per_day"]) == 30
    assert sum(n for _, n in detail["per_day"]) == 6
    assert len(detail["recent"]) == 7


def test_users_list_rows_and_threshold(world) -> None:
    rows = {r["row_nickname"]: people.decorate(r) for r in people.user_rows()}
    alice, bob, carl = rows["Alice"], rows["Bob"], rows["Carl"]
    assert (alice["games"], alice["wins"], alice["losses"]) == (9, 5, 4)
    assert alice["win_rate"] == pytest.approx(5 / 9)
    assert alice["favorite"] == "rps" and alice["row_username"] == "alice"
    assert (bob["games"], bob["wins"]) == (3, 3) and bob["win_rate"] is None  # < 5 games
    assert carl["is_guest"] and carl["short_key"] == "c" * 8 and carl["row_username"] == ""
    assert (carl["games"], carl["wins"]) == (6, 2) and carl["win_rate"] == pytest.approx(2 / 6)
    dana = rows["Dana"]
    assert dana["games"] == 0 and dana["wins"] == 0  # abandoned only


def test_users_list_sort_filter_search(world) -> None:
    by_games = [r["row_nickname"] for r in people.user_rows(sort="games")]
    assert by_games == ["Alice", "Carl", "Bob", "Dana"]
    by_rate = [r["row_nickname"] for r in people.user_rows(sort="win_rate")]
    assert by_rate[:2] == ["Alice", "Carl"] and set(by_rate[2:]) == {"Bob", "Dana"}
    assert [r["row_nickname"] for r in people.user_rows(kind="guest")] == ["Carl", "Dana"]
    assert [r["row_nickname"] for r in people.user_rows(search="BO")] == ["Bob"]
    assert [r["row_nickname"] for r in people.user_rows(search="dan")] == ["Dana"]
    asc = [r["row_nickname"] for r in people.user_rows(sort="wins", desc=False)]
    assert asc[0] == "Dana"


def test_users_page_shows_dash_below_threshold_and_paginates(world, settings) -> None:
    client = staff_client()
    html = client.get(M + "dashboard/users/").content.decode()
    assert "56%" in html  # Alice 5/9
    assert "approximate (browser-based)" in html
    from analytics import dashboard

    original = dashboard.DASHBOARD_PAGE_SIZE
    dashboard.DASHBOARD_PAGE_SIZE = 2
    try:
        first = client.get(M + "dashboard/users/?sort=games").content.decode()
        second = client.get(M + "dashboard/users/?sort=games&page=2").content.decode()
    finally:
        dashboard.DASHBOARD_PAGE_SIZE = original
    assert "Page 1 of 2" in first and ">Alice<" in first and ">Bob<" not in first
    assert ">Bob<" in second and "sort=games&page=1" in second


def test_user_detail_numbers_and_tie_breaks(world) -> None:
    alice = world["alice"]
    detail = people.actor_detail(people.Actor("registered", alice, ""))
    t = detail["totals"]
    assert (t["games"], t["wins"], t["losses"], t["abandoned"]) == (9, 5, 4, 1)
    per = {g["id"]: g for g in detail["per_game"]}
    assert (per["rps"]["played"], per["rps"]["wins"], per["rps"]["losses"]) == (6, 4, 2)
    assert per["hangman"]["avg_placement"] == pytest.approx(5 / 3)
    assert detail["most_played"]["id"] == "rps"
    assert detail["most_won"]["id"] == "rps"
    assert detail["most_lost"]["id"] in {"rps", "hangman"}  # 2 losses each: lower rate wins
    assert detail["most_lost"]["id"] == "hangman"  # 1/3 < 4/6
    assert len(detail["recent"]) == 10
    abandoned = [p for p in detail["recent"] if p.placement is None]
    assert abandoned and abandoned[0].opponents == ["Dana"]
    co = {c["name"]: c for c in detail["co_players"]}
    assert (co["Carl"]["shared"], co["Carl"]["ahead"], co["Carl"]["behind"]) == (6, 4, 2)
    assert (co["Bob"]["shared"], co["Bob"]["ahead"], co["Bob"]["behind"]) == (3, 0, 2)
    assert "Dana" not in co  # abandoned games are not shared completed games
    assert [e.kind for e in detail["events"]] == ["login"]


def test_most_won_tie_break_prefers_higher_win_rate() -> None:
    per_game = [
        {"id": "a", "name": "A", "played": 10, "wins": 3, "losses": 7},
        {"id": "b", "name": "B", "played": 4, "wins": 3, "losses": 1},
        {"id": "c", "name": "C", "played": 9, "wins": 2, "losses": 7},
    ]
    assert people.pick_most(per_game, "wins", prefer_high_rate=True)["id"] == "b"
    assert people.pick_most(per_game, "losses", prefer_high_rate=False)["id"] == "c"
    assert people.pick_most([{**g, "wins": 0} for g in per_game], "wins", True) is None


def test_guest_detail(world) -> None:
    detail = people.actor_detail(people.Actor("guest", None, GUEST_CARL))
    assert (detail["totals"]["games"], detail["totals"]["wins"]) == (6, 2)
    assert detail["totals"]["win_rate"] == pytest.approx(2 / 6)
    assert [e.kind for e in detail["events"]] == ["room_joined"]


def test_leaderboards(world) -> None:
    boards = people.leaderboards(None)
    assert [r["name"] for r in boards["most_wins"]] == ["Alice", "Bob", "Carl"]
    assert [r["name"] for r in boards["best_rate"]] == ["Alice", "Carl"]  # Bob < 5 games
    assert [r["name"] for r in boards["most_games"]][:2] == ["Alice", "Carl"]
    hangman = people.leaderboards("hangman")
    assert [r["name"] for r in hangman["most_wins"]] == ["Bob", "Alice"]
    assert hangman["best_rate"] == []


def test_deleted_players_stay_in_totals_not_in_people_views(world) -> None:
    from accounts.services import delete_account

    bob = world["bob"]
    PlayerStats.objects.create(user=bob, game_id="hangman", played=3, wins=3)
    delete_account(bob)
    assert metrics.games_table(metrics.parse_range("all"))[1]["plays"] == 3  # hangman kept
    assert GameParticipation.objects.filter(nickname=DELETED_NICKNAME).count() == 3
    names = {r["row_nickname"] for r in people.user_rows()}
    assert "Bob" not in names and DELETED_NICKNAME not in names
    assert "Deleted player" not in [r["name"] for r in people.leaderboards(None)["most_wins"]]


# ----- query counts ------------------------------------------------------------------


def _queries(client: Client, url: str) -> int:
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    cache.clear()
    with CaptureQueriesContext(connection) as ctx:
        assert client.get(url).status_code == 200
    return len(ctx.captured_queries)


def test_page_queries_do_not_grow_with_data(world) -> None:
    client = staff_client()
    alice = world["alice"]
    urls = [
        M,
        M + "dashboard/games/",
        M + "dashboard/games/rps/",
        M + "dashboard/users/",
        M + f"dashboard/users/u/{alice.pk}/",
        M + "dashboard/leaderboards/",
        M + "dashboard/activity/",
    ]
    before = {url: _queries(client, url) for url in urls}
    for i in range(15):
        guest = f"{i:016x}"
        extra = account(f"extra{i}", f"Extra{i}")
        play("rps", [(alice, "Alice", 1), (guest, f"G{i}", 2), (extra, f"Extra{i}", 3)])
        ActivityEvent.objects.create(kind="room_joined", occurred_at=timezone.now(), user=extra)
    after = {url: _queries(client, url) for url in urls}
    assert after == before
    assert all(n <= 15 for n in after.values()), after


def test_main_pages_query_budget(world, django_assert_max_num_queries) -> None:
    client = staff_client()
    for url, budget in [
        (M + "?range=all", 12),
        (M + "dashboard/users/", 10),
        (M + "dashboard/games/", 8),
        (M + f"dashboard/users/u/{world['alice'].pk}/", 14),
    ]:
        cache.clear()
        with django_assert_max_num_queries(budget):
            client.get(url)


# ----- live now ----------------------------------------------------------------------


def test_live_now_snapshot_shows_no_secrets(monkeypatch) -> None:
    fake = RoomManager()
    room = Room(code="WXYZ", host_id="p_secretseat", created_at=0, last_activity=0)
    room.players.append(
        Player(
            id="p_secretseat",
            profile_id="raw-profile-id-123",
            nickname="Zed",
            color=PLAYER_COLORS[0],
            avatar=Avatar("cutouts", "a"),
            joined_at=0,
            token="room-token-abc",
            guest_key="f" * 16,
        )
    )
    room.status, room.game_id, room.game_state = "playing", "rps", {"secret": "hidden-move"}
    fake.rooms[room.code] = room
    monkeypatch.setattr(manager_module, "manager", fake)
    html = staff_client().get(M).content.decode()
    assert "WXYZ" in html and "Rock" in html
    for secret in ["p_secretseat", "raw-profile-id-123", "room-token-abc", "hidden-move", "f" * 16]:
        assert secret not in html


# ----- CSV ---------------------------------------------------------------------------


def _csv(client: Client, url: str) -> list[list[str]]:
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert response.streaming
    return list(csv.reader(io.StringIO(b"".join(response.streaming_content).decode())))


def test_users_csv(world) -> None:
    rows = _csv(staff_client(), M + "dashboard/export/users.csv")
    assert rows[0][:4] == ["type", "key", "username", "nickname"]
    body = {r[3]: r for r in rows[1:]}
    assert body["Alice"][0] == "registered" and body["Alice"][2] == "alice"
    assert body["Alice"][6:9] == ["9", "5", "4"] and body["Alice"][9] == "0.5556"
    assert body["Bob"][9] == ""  # below the rate threshold
    assert body["Carl"][0] == "guest" and body["Carl"][1] == "c" * 8


def test_sessions_csv(world) -> None:
    rows = _csv(staff_client(), M + "dashboard/export/sessions.csv")
    assert rows[0][0:3] == ["id", "game_id", "status"]
    assert len(rows) == 1 + 10
    abandoned = [r for r in rows[1:] if r[2] == "abandoned"]
    assert abandoned[0][7:10] == ["1", "1", "0"]  # registered, guests, winners


def test_csv_is_staff_only(world) -> None:
    player = account("player", "Player")
    client = Client(HTTP_HOST="localhost")
    client.force_login(player)
    assert client.get(M + "dashboard/export/users.csv").status_code == 302


# ----- admin actions -----------------------------------------------------------------


def test_disable_and_enable_from_user_detail(world) -> None:
    client = staff_client()
    alice = world["alice"]
    url = M + f"dashboard/users/u/{alice.pk}/"
    assert client.post(url + "disable/").status_code == 302
    alice.refresh_from_db()
    assert not alice.is_active
    assert client.post(url + "enable/").status_code == 302
    alice.refresh_from_db()
    assert alice.is_active
    messages = list(LogEntry.objects.order_by("id").values_list("change_message", flat=True))
    assert messages == ["Disabled account", "Enabled account"]
    assert (
        client.get(url + "disable/").status_code == 302 and User.objects.get(pk=alice.pk).is_active
    )


def test_disabled_account_token_stops_working(world) -> None:
    alice = world["alice"]
    token = issue_token(alice.pk)
    staff_client().post(M + f"dashboard/users/u/{alice.pk}/disable/")
    me = Client(HTTP_HOST="localhost").get("/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert me.status_code == 401


def test_delete_from_user_detail_confirms_then_anonymises(world) -> None:
    client = staff_client()
    alice = world["alice"]
    url = M + f"dashboard/users/u/{alice.pk}/delete/"
    confirm = client.get(url)
    assert confirm.status_code == 200 and b"cannot be undone" in confirm.content
    assert User.objects.filter(pk=alice.pk).exists()
    assert client.post(url).status_code == 302
    assert not User.objects.filter(pk=alice.pk).exists()
    assert GameParticipation.objects.filter(nickname=DELETED_NICKNAME).count() == 10
    assert GameSession.objects.count() == 10
    assert LogEntry.objects.filter(action_flag=3, object_repr="alice").exists()
    assert ActivityEvent.objects.filter(kind="login", user__isnull=True).exists()


def test_changelist_actions(world) -> None:
    client = staff_client()
    bob = world["bob"]
    changelist = M + "auth/user/"
    page = client.get(changelist).content.decode()
    assert "delete_selected_accounts" in page and 'value="delete_selected"' not in page
    client.post(changelist, {"action": "disable_accounts", "_selected_action": [bob.pk]})
    assert not User.objects.get(pk=bob.pk).is_active
    client.post(changelist, {"action": "enable_accounts", "_selected_action": [bob.pk]})
    assert User.objects.get(pk=bob.pk).is_active
    confirm = client.post(
        changelist, {"action": "delete_selected_accounts", "_selected_action": [bob.pk]}
    )
    assert confirm.status_code == 200 and User.objects.filter(pk=bob.pk).exists()
    client.post(
        changelist,
        {"action": "delete_selected_accounts", "_selected_action": [bob.pk], "confirmed": "yes"},
    )
    assert not User.objects.filter(pk=bob.pk).exists()
    assert GameParticipation.objects.filter(nickname=DELETED_NICKNAME).count() == 3
    assert LogEntry.objects.filter(object_repr="bob", action_flag=3).exists()


def test_admin_change_page_delete_also_anonymises(world) -> None:
    client = staff_client()
    alice = world["alice"]
    response = client.post(M + f"auth/user/{alice.pk}/delete/", {"post": "yes"})
    assert response.status_code == 302
    assert not User.objects.filter(pk=alice.pk).exists()
    assert GameParticipation.objects.filter(nickname=DELETED_NICKNAME).count() == 10


# ----- no secrets anywhere -----------------------------------------------------------


def test_no_secret_fields_on_any_page(world) -> None:
    client = staff_client()
    alice = world["alice"]
    token = issue_token(alice.pk)
    html = "".join(
        client.get(M + page).content.decode()
        for page in PAGES
        + [
            f"dashboard/users/u/{alice.pk}/",
            f"dashboard/users/g/{GUEST_CARL}/",
        ]
    )
    for export in ("users", "sessions"):
        response = client.get(M + f"dashboard/export/{export}.csv")
        html += b"".join(response.streaming_content).decode()
    assert alice.password not in html  # the password hash
    assert "pbkdf2" not in html and "md5$" not in html
    assert token not in html
    assert "127.0.0.1" not in html
    assert "roomToken" not in html and "profileId" not in html
