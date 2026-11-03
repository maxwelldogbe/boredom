"""Games staff turn off from the dashboard: hidden from rooms, never selected or started."""

import pytest
from channels.db import database_sync_to_async
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.test import Client

from analytics.models import GameAvailability
from games import availability
from tests.conftest import make_profile
from tests.dashboard_data import PASSWORD

pytestmark = pytest.mark.django_db(transaction=True)

A = "/api/admin/"


def staff_client(superuser: bool = True) -> Client:
    maker = User.objects.create_superuser if superuser else User.objects.create_user
    boss = maker(username="boss", password=PASSWORD, **({} if superuser else {"is_staff": True}))
    client = Client(HTTP_HOST="localhost")
    client.force_login(boss)
    return client


async def lobby(connect, game: str = "dummy"):
    """A two-player room with `game` selected and the guest ready. Returns (code, host, guest)."""
    host = await connect()
    created = await host.request("room:create", {"profile": make_profile("Hana")})
    code = created["data"]["room"]["code"]
    guest = await connect()
    assert (await guest.request("room:join", {"code": code, "profile": make_profile("Gil")}))["ok"]
    assert (await host.request("room:selectGame", {"gameId": game, "settings": {}}))["ok"]
    assert (await guest.request("room:ready", {"ready": True}))["ok"]
    return code, host, guest


# ----- the admin API -------------------------------------------------------------------


def test_games_list_shows_switches() -> None:
    data = staff_client().get(A + "games").json()
    assert data["permissions"] == {"toggle": True}
    assert all(g["enabled"] for g in data["games"])


def test_disable_and_enable_a_game(monkeypatch) -> None:
    from rooms import manager as manager_module

    calls = []
    monkeypatch.setattr(manager_module.manager, "games_changed_soon", lambda: calls.append(1))
    client = staff_client()
    response = client.post(A + "games/rps/disable")
    assert response.json() == {"ok": True, "enabled": False}
    assert availability.disabled() == {"rps"}
    assert not GameAvailability.objects.get(game_id="rps").enabled
    rows = {g["id"]: g for g in client.get(A + "games").json()["games"]}
    assert rows["rps"]["enabled"] is False and rows["hangman"]["enabled"] is True
    assert LogEntry.objects.filter(change_message="Turned Rock-Paper-Scissors off").exists()
    client.post(A + "games/rps/disable")  # no change: no new log, no room update
    assert len(calls) == 1
    assert client.post(A + "games/rps/enable").json()["enabled"] is True
    assert availability.disabled() == frozenset() and len(calls) == 2


def test_the_switch_survives_a_restart() -> None:
    staff_client().post(A + "games/hangman/disable")
    availability.reset(None)  # a fresh process
    assert availability.load() == {"hangman"}


def test_game_action_errors() -> None:
    client = staff_client()
    assert client.post(A + "games/nope/disable").status_code == 404
    assert client.post(A + "games/rps/explode").status_code == 404
    assert client.get(A + "games/rps/disable").status_code == 405
    assert Client(HTTP_HOST="localhost").post(A + "games/rps/disable").status_code == 401


def test_staff_need_the_change_permission() -> None:
    client = staff_client(superuser=False)
    assert client.get(A + "games").json()["permissions"] == {"toggle": False}
    assert client.post(A + "games/rps/disable").status_code == 403
    boss = User.objects.get(username="boss")
    boss.user_permissions.add(Permission.objects.get(codename="change_gameavailability"))
    assert client.post(A + "games/rps/disable").status_code == 200


# ----- rooms ---------------------------------------------------------------------------


async def test_room_state_lists_off_games(connect) -> None:
    availability.reset(frozenset({"rps"}))
    host = await connect()
    created = await host.request("room:create", {"profile": make_profile("Hana")})
    assert created["data"]["room"]["disabledGames"] == ["rps"]


async def test_off_game_cannot_be_selected_or_started(connect, manager) -> None:
    code, host, _ = await lobby(connect)
    availability.reset(frozenset({"dummy", "rps"}))
    ack = await host.request("room:selectGame", {"gameId": "rps", "settings": {}})
    assert ack["error"]["code"] == "GAME_DISABLED"
    assert (await host.request("game:start"))["error"]["code"] == "GAME_DISABLED"
    assert manager.rooms[code].status == "lobby"


async def test_turning_off_clears_lobby_selection(connect, manager) -> None:
    code, host, guest = await lobby(connect)
    availability.reset(frozenset({"dummy"}))
    await manager.games_changed()
    room = manager.rooms[code]
    assert room.selected_game is None and room.settings == {}
    assert not any(p.ready for p in room.players)
    event = await guest.wait_push("room:event", lambda d: d["kind"] == "game_unselected")
    assert event["data"] == {"reason": "disabled"}
    state = await guest.wait_push("room:state", lambda d: d["disabledGames"] == ["dummy"])
    assert state["selectedGame"] is None


async def test_running_game_finishes_then_is_dropped(connect, manager) -> None:
    code, host, _ = await lobby(connect)
    assert (await host.request("game:start"))["ok"]
    availability.reset(frozenset({"dummy"}))
    await manager.games_changed()
    room = manager.rooms[code]
    assert room.status == "playing" and room.selected_game == "dummy"
    room.status = "finished"
    assert (await host.request("game:playAgain"))["ok"]
    assert room.status == "lobby" and room.selected_game is None


async def test_ensure_loaded_reads_the_table(connect) -> None:
    await database_sync_to_async(GameAvailability.objects.create)(game_id="rps", enabled=False)
    availability.reset(None)
    host = await connect()
    created = await host.request("room:create", {"profile": make_profile("Hana")})
    assert created["data"]["room"]["disabledGames"] == ["rps"]
