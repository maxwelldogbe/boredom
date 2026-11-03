"""Solo rooms (rooms/solo.py): one player against a bot, private, recorded only as SoloRecord."""

import asyncio
import random

import pytest
from channels.db import database_sync_to_async

from accounts.models import PlayerStats
from analytics.models import ActivityEvent, GameParticipation, GameSession
from bots import CHOOSERS
from nemesis.models import LedgerTransaction
from rooms import hooks
from solo.models import SoloRecord
from tests.conftest import make_profile
from tests.test_accounts_ws import make_account
from tests.test_guest_quota import plays

pytestmark = pytest.mark.django_db(transaction=True)

PREFERRED = (3, 4, 5, 6, 7, 8, 0, 1, 2)  # the player's cells, in order of preference


def lowest(view, rng, difficulty, budget_ms):
    """A predictable stand-in bot: the lowest empty cell."""
    return {"type": "place", "cell": min(view["legalMoves"])}


@pytest.fixture
def quick_bot(manager):
    manager.bot_think_ms = (0, 0)
    return manager


async def solo(connect, username="solo_sam", game="tic_tac_toe", variant=None):
    user, token = await make_account(username, "Sam")
    client = await connect()
    payload = {
        "authToken": token,
        "gameId": game,
        "variant": {"difficulty": "easy"} if variant is None else variant,
    }
    ack = await client.request("solo:start", payload)
    assert ack["ok"], ack
    return user, token, client, ack["data"]


async def my_turn_or_over(client):
    def ready(d):
        view = d["view"]
        return view["phase"] == "done" or view["match"]["game"]["isYourTurn"]

    return (await client.wait_push("game:view", ready))["view"]


async def play_out(client):
    """Play the game to the end with PREFERRED cells; return the final view with soloResult."""
    while True:
        view = await my_turn_or_over(client)
        if view["phase"] == "done":
            if view["soloResult"]:
                return view
            return (await client.wait_push("game:view", lambda d: d["view"]["soloResult"]))["view"]
        legal = view["match"]["game"]["legalMoves"]
        cell = next(c for c in PREFERRED if c in legal)
        assert (await client.request("game:action", {"type": "place", "cell": cell}))["ok"]


@database_sync_to_async
def counts():
    return {
        "records": list(SoloRecord.objects.values("game_id", "variant", "plays", "wins")),
        "events": sorted(ActivityEvent.objects.values_list("kind", flat=True)),
        "stats": PlayerStats.objects.count(),
        "sessions": GameSession.objects.count() + GameParticipation.objects.count(),
        "nemesis": LedgerTransaction.objects.count(),
    }


async def test_guests_and_bad_requests_are_rejected(connect, manager) -> None:
    guest = await connect()
    ack = await guest.request("solo:start", {"profile": make_profile("Gus"), "gameId": "rps"})
    assert ack["error"]["code"] == "REGISTERED_ONLY"
    _, token = await make_account("solo_bad", "Bad")
    for payload in (
        {"gameId": "rps"},
        {"gameId": "tic_tac_toe", "variant": {"difficulty": "insane"}},
    ):
        ack = await guest.request("solo:start", {"authToken": token, **payload})
        assert ack["error"]["code"] == "INVALID_ACTION"
    assert manager.rooms == {}


async def test_start_joins_and_starts_with_a_visible_bot(connect, manager, quick_bot) -> None:
    _, _, client, data = await solo(connect, variant={})
    room = manager.rooms[data["code"]]
    assert data["roomToken"] and room.status == "playing" and room.solo
    state = data["room"]
    assert state["solo"] is True and state["soloVariant"] == {"difficulty": "medium"}
    me, bot = state["players"]
    assert me["bot"] is False and me["type"] == "registered"
    assert bot == {**bot, "bot": True, "type": "bot", "nickname": "Bot", "avatar": None}
    view = await client.wait_push("game:view")
    assert view["gameId"] == "tic_tac_toe" and view["view"]["bestOf"] == 1
    assert view["view"]["soloResult"] is None


async def test_one_solo_room_per_account(connect, manager, quick_bot, recording) -> None:
    _, token, client, first = await solo(connect)
    other = await connect()
    ack = await other.request("solo:start", {"authToken": token, "gameId": "connect_four"})
    assert ack["ok"]
    assert first["code"] not in manager.rooms and ack["data"]["code"] in manager.rooms
    await hooks.drain()
    found = await counts()
    assert found["records"] == [] and found["events"] == ["solo_started", "solo_started"]


async def test_private_room_and_presence(connect, manager, quick_bot) -> None:
    _, token, client, data = await solo(connect)
    code = data["code"]
    assert (await client.request("auth:hello", {"authToken": token}))["ok"]
    assert manager.social.status(manager.rooms[code].solo_owner) == "in_game"
    stranger = await connect()
    assert (await stranger.request("room:peek", {"code": code}))["data"]["exists"] is False
    _, other_token = await make_account("solo_stranger", "Stan")
    for payload in ({"authToken": other_token}, {"profile": make_profile("Gus")}):
        ack = await stranger.request("room:join", {"code": code, **payload})
        assert ack["error"]["code"] == "ROOM_NOT_FOUND"
    assert (await client.request("room:react", {"emoji": "👏"}))["error"]["code"] == (
        "INVALID_ACTION"
    )
    back = await connect()
    ack = await back.request(
        "room:join", {"code": code, "authToken": token, "roomToken": data["roomToken"]}
    )
    assert ack["ok"] and len(manager.rooms[code].players) == 2


async def test_bot_waits_its_think_time_and_acts_once(connect, manager, monkeypatch) -> None:
    calls = []

    def counting(view, rng, difficulty, budget_ms):
        calls.append(view["turn"])
        return lowest(view, rng, difficulty, budget_ms)

    monkeypatch.setitem(CHOOSERS, "tic_tac_toe", counting)
    manager.bot_think_ms = (150, 150)
    _, _, client, data = await solo(connect)
    room = manager.rooms[data["code"]]
    view = await my_turn_or_over(client)
    marks = sum(v is not None for v in view["match"]["game"]["board"])
    loop = asyncio.get_running_loop()
    start = loop.time()
    assert (await client.request("game:action", {"type": "place", "cell": 4}))["ok"]
    async with room.lock:  # a second schedule replaces the first: still one move
        manager._drive_bot(room)
    view = await my_turn_or_over(client)
    assert loop.time() - start >= 0.14
    assert sum(v is not None for v in view["match"]["game"]["board"]) == marks + 2
    await asyncio.sleep(0.3)
    assert len(calls) == marks + 1 and room.bot_task is None
    assert (await client.request("game:action", {"type": "place", "cell": 8}))["ok"]
    assert (await client.request("solo:quit"))["ok"]
    await asyncio.sleep(0.3)
    assert data["code"] not in manager.rooms and len(calls) == marks + 1


async def test_finishing_records_only_the_solo_record(
    connect, manager, quick_bot, recording, monkeypatch
) -> None:
    monkeypatch.setitem(CHOOSERS, "tic_tac_toe", lowest)
    user, _, client, data = await solo(connect)
    room = manager.rooms[data["code"]]
    final = await play_out(client)
    result = final["soloResult"]
    outcome = result["outcome"]
    assert outcome in ("win", "lose", "draw")
    expected = {"win": (1, 0, 0), "lose": (0, 1, 0), "draw": (0, 0, 1)}[outcome]
    wins, losses, draws = expected
    assert result["record"] == {"plays": 1, "wins": wins, "losses": losses, "draws": draws}
    assert room.status == "finished" and room.scoreboard == {} and room.wins == {}
    await hooks.drain()
    found = await counts()
    assert found["records"] == [
        {"game_id": "tic_tac_toe", "variant": "easy", "plays": 1, "wins": expected[0]}
    ]
    assert found["events"] == ["solo_finished", "solo_started"]
    assert found["stats"] == found["sessions"] == found["nemesis"] == 0
    assert await plays() == {}


async def test_again_alternates_the_first_mover(connect, manager, quick_bot, monkeypatch) -> None:
    monkeypatch.setitem(CHOOSERS, "tic_tac_toe", lowest)
    manager.rng_factory = lambda: random.Random(5)
    _, _, client, data = await solo(connect)
    room = manager.rooms[data["code"]]
    firsts = [room.solo_first]
    assert (await client.request("solo:again"))["error"]["code"] == "GAME_IN_PROGRESS"
    for _ in range(2):
        await play_out(client)
        assert (await client.request("solo:again"))["ok"]
        firsts.append(room.solo_first)
    assert firsts[0] != firsts[1] != firsts[2]
    assert set(firsts) == {p.id for p in room.players}


async def test_quit_and_idle_close_record_nothing(connect, manager, quick_bot, recording) -> None:
    _, _, client, data = await solo(connect)
    assert (await client.request("solo:quit"))["ok"]
    assert data["code"] not in manager.rooms
    manager.solo_idle_ms = 100
    _, _, idle, data = await solo(connect, "solo_idle")
    await idle.close()
    await asyncio.sleep(0.05)
    assert data["code"] in manager.rooms  # not yet
    await asyncio.sleep(0.2)
    assert data["code"] not in manager.rooms
    await hooks.drain()
    found = await counts()
    assert found["records"] == [] and "solo_finished" not in found["events"]
    assert found["sessions"] == 0 and found["events"].count("solo_started") == 2
