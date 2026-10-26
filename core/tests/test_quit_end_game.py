"""Integration: game:quit, game:end, room:leave forfeits, offline forfeits and room:event."""

import asyncio

import pytest

from rooms import hooks
from tests.conftest import make_profile
from tests.test_rooms_lifecycle import offline_at, setup_room, start


def events(client, kind):
    """Buffered room:event pushes of `kind`, without consuming them."""
    pushes = [p["data"] for p in client.pushes if p["type"] == "room:event"]
    return [e for e in pushes if e["kind"] == kind]


def in_game_at(index, value):
    """Predicate: the room:state shows the seat at `index` with inGame == value."""
    return lambda d: len(d["players"]) > index and d["players"][index]["inGame"] is value


async def rejoin(connect, code, name, token):
    client = await connect()
    payload = {"code": code, "profile": make_profile(name), "roomToken": token}
    assert (await client.request("room:join", payload))["ok"]
    return client


async def game_over(client):
    """The gameOver results keyed by player id, then the finished room:state."""
    over = await client.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    state = await client.wait_push("room:state", lambda d: d["status"] == "finished")
    return {r["playerId"]: r for r in over["data"]["results"]}, state


# ----- game:quit ------------------------------------------------------------------------------


async def test_quit_keeps_the_player_in_the_room_and_the_game_goes_on(connect, manager):
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"), {"target": 3})
    await start([host, ann, bob])
    assert (await ann.request("game:quit"))["ok"]
    quit_event = await host.wait_push("room:event", lambda d: d["kind"] == "player_quit")
    assert quit_event == {"kind": "player_quit", "playerId": ann.player_id, "nickname": "Ann"}
    state = await bob.wait_push("room:state", lambda d: not d["players"][1]["inGame"])
    assert state["status"] == "playing" and len(state["players"]) == 3
    assert state["players"][1]["online"] and state["hostId"] == host.player_id
    assert (await ann.request("game:action", {"type": "score"}))["error"]["code"] == (
        "INVALID_ACTION"
    )
    assert (await ann.request("game:quit"))["error"]["code"] == "INVALID_ACTION"
    assert (await host.request("game:action", {"type": "score"}))["ok"]


async def test_quit_without_a_running_game_is_rejected(connect):
    code, (host, ann) = await setup_room(connect)
    assert (await ann.request("game:quit"))["error"]["code"] == "INVALID_ACTION"


async def test_host_who_quits_stays_host(connect, manager):
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"))
    await start([host, ann, bob])
    assert (await host.request("game:quit"))["ok"]
    state = await ann.wait_push("room:state", lambda d: not d["players"][0]["inGame"])
    assert state["hostId"] == host.player_id
    await ann.drain()
    assert not events(ann, "host_changed")


async def test_min_players_only_matters_at_the_start(connect, manager, dummy_game, monkeypatch):
    monkeypatch.setattr(dummy_game, "min_players", 3)
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"), {"target": 5})
    await start([host, ann, bob])
    assert (await bob.request("game:quit"))["ok"]
    await host.drain()
    assert manager.rooms[code].status == "playing"
    assert (await host.request("game:action", {"type": "score"}))["ok"]


# ----- one player left: an immediate win, the same through every forfeit path --------------


@pytest.mark.parametrize("how", ["quit", "leave", "offline"])
async def test_two_player_game_ends_at_once_on_any_forfeit(connect, manager, how):
    manager.offline_forfeit_ms = 100
    code, (host, ann) = await setup_room(connect, settings={"target": 5})
    await start([host, ann])
    await host.request("game:action", {"type": "score"})
    await ann.request("game:action", {"type": "score"})
    if how == "quit":
        assert (await ann.request("game:quit"))["ok"]
    elif how == "leave":
        assert (await ann.request("room:leave"))["ok"]
    else:
        await ann.close()
    results, state = await game_over(host)
    assert results[host.player_id]["placement"] == 1 and results[host.player_id]["points"] == 100
    assert results[ann.player_id]["placement"] == 2 and results[ann.player_id]["points"] == 0
    assert state["endReason"] == "forfeit"
    assert state["wins"] == {host.player_id: 1}
    assert all(p["inGame"] for p in state["players"])
    assert manager.rooms[code].timer_task is None and not manager.rooms[code].forfeit_tasks


async def test_forfeiters_rank_last_latest_first(connect, manager):
    names = ("Host", "Ann", "Bob", "Cat")
    code, (host, ann, bob, cat) = await setup_room(connect, names, {"target": 2})
    await start([host, ann, bob, cat])
    await host.request("game:action", {"type": "score"})
    await ann.request("game:action", {"type": "score"})  # Ann leads with Host
    assert (await ann.request("game:quit"))["ok"]
    assert (await bob.request("room:leave"))["ok"]
    assert (await cat.request("game:action", {"type": "score"}))["ok"]
    assert (await host.request("game:action", {"type": "score"}))["ok"]  # Host reaches 2
    results, state = await game_over(host)
    assert {pid: r["placement"] for pid, r in results.items()} == {
        host.player_id: 1, cat.player_id: 2, bob.player_id: 3, ann.player_id: 4,
    }
    assert results[ann.player_id]["score"] == 1  # raw score is kept, the placement is not
    assert [results[p]["points"] for p in (host.player_id, cat.player_id, bob.player_id)] == [
        100, 66.67, 33.33,
    ]
    assert state["endReason"] == "completed"
    assert [p["nickname"] for p in state["players"]] == ["Host", "Ann", "Cat"]  # Bob left


async def test_last_player_forfeiting_abandons_the_session(connect, manager, monkeypatch):
    abandoned = []
    monkeypatch.setattr(hooks, "on_game_abandoned", abandoned.append)
    code, (host, ann) = await setup_room(connect, ("Host", "Ann"))
    room = manager.rooms[code]
    assert (await ann.request("room:leave"))["ok"]
    await host.drain()
    assert (await host.request("game:start"))["ok"]
    assert (await host.request("game:quit"))["ok"]
    state = await host.wait_push("room:state", lambda d: d["endReason"] == "forfeit")
    assert state["status"] == "lobby" and state["scoreboard"] == {}
    assert abandoned[0].results is None and abandoned[0].forfeited == {host.player_id}
    assert room.game_state is None


# ----- game:end ---------------------------------------------------------------------------------


async def test_end_game_is_host_only_and_needs_a_game(connect, manager):
    code, (host, ann) = await setup_room(connect)
    assert (await host.request("game:end"))["error"]["code"] == "INVALID_ACTION"
    await start([host, ann])
    assert (await ann.request("game:end"))["error"]["code"] == "NOT_HOST"
    assert manager.rooms[code].status == "playing"


async def test_end_game_returns_to_lobby_without_results(connect, manager, monkeypatch):
    abandoned, finished = [], []
    monkeypatch.setattr(hooks, "on_game_abandoned", abandoned.append)
    monkeypatch.setattr(hooks, "on_game_finished", finished.append)
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"), {"target": 1})
    await start([host, ann, bob])
    assert (await host.request("game:action", {"type": "score"}))["ok"]  # a first game
    await game_over(ann)
    scoreboard = dict(manager.rooms[code].scoreboard)
    assert (await host.request("game:playAgain"))["ok"]
    await start([host, ann, bob])
    assert (await bob.request("game:quit"))["ok"]
    await ann.drain()
    ann.pushes.clear()
    assert (await host.request("game:end"))["ok"]
    ended = await ann.wait_push("room:event", lambda d: d["kind"] == "game_ended_by_host")
    assert ended["playerId"] == host.player_id
    state = await ann.wait_push("room:state", lambda d: d["status"] == "lobby")
    assert state["endReason"] == "host_ended" and state["scoreboard"] == scoreboard
    assert all(p["inGame"] for p in state["players"])
    await ann.drain()
    assert not [p for p in ann.pushes if p["type"] == "game:event"]
    assert len(abandoned) == 1 and abandoned[0].results is None and len(finished) == 1
    room = manager.rooms[code]
    assert room.timer_task is None and room.game_state is None and room.game_id is None
    assert (await host.request("game:start"))["ok"]


# ----- reconnects, inGame and endReason --------------------------------------------------------


async def test_quitter_who_reconnects_stays_out_of_the_game(connect, manager):
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"))
    await start([host, ann, bob])
    assert (await ann.request("game:quit"))["ok"]
    token = ann.token
    await ann.close()
    back = await rejoin(connect, code, "Ann", token)
    state = await back.wait_push("room:state")
    assert state["players"][1]["online"] and state["players"][1]["inGame"] is False
    assert (await back.request("game:action", {"type": "score"}))["error"]["code"] == (
        "INVALID_ACTION"
    )
    assert (await back.wait_push("game:view"))["gameId"] == "dummy"  # still watches


async def test_end_reason_completed_then_cleared_on_next_start(connect, manager):
    code, (host, ann) = await setup_room(connect, settings={"target": 1})
    await start([host, ann])
    assert (await host.request("game:action", {"type": "score"}))["ok"]
    _, state = await game_over(ann)
    assert state["endReason"] == "completed"
    assert (await host.request("game:playAgain"))["ok"]
    assert manager.rooms[code].end_reason == "completed"
    assert (await host.request("game:start"))["ok"]
    state = await ann.wait_push("room:state", lambda d: d["status"] == "playing")
    assert state["endReason"] is None


async def test_offline_forfeit_is_cancelled_by_a_reconnect(connect, manager):
    manager.offline_forfeit_ms = 300
    code, (host, ann) = await setup_room(connect)
    await start([host, ann])
    token = ann.token
    await ann.close()
    await host.wait_push("room:state", offline_at(1))
    back = await rejoin(connect, code, "Ann", token)
    await asyncio.sleep(0.4)
    assert manager.rooms[code].status == "playing"
    assert manager.rooms[code].player(back.player_id).in_game


async def test_offline_at_start_is_forfeited_after_the_delay(connect, manager):
    manager.offline_forfeit_ms = 100
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"))
    await bob.close()
    await host.wait_push("room:state", offline_at(2))
    assert (await host.request("game:start"))["ok"]
    forfeit = await host.wait_push("game:event", lambda d: d["kind"] == "forfeit")
    assert forfeit["data"] == {"playerId": bob.player_id, "reason": "offline"}
    state = await host.wait_push("room:state", in_game_at(2, False))
    assert state["status"] == "playing" and state["players"][2]["offlineSince"] is not None


# ----- offline notices ---------------------------------------------------------------------------


async def test_quick_reconnect_sends_no_notice(connect, manager):
    manager.offline_notice_ms = 300
    code, (host, ann) = await setup_room(connect)
    token = ann.token
    await ann.close()
    await rejoin(connect, code, "Ann", token)
    await asyncio.sleep(0.4)
    await host.drain()
    assert not events(host, "player_offline") and not events(host, "player_online")


async def test_offline_notice_after_the_delay_then_online(connect, manager):
    manager.offline_notice_ms = 50
    code, (host, ann) = await setup_room(connect)
    token = ann.token
    await ann.close()
    state = await host.wait_push("room:state", offline_at(1))
    assert state["players"][1]["offlineSince"] is not None
    offline = await host.wait_push("room:event", lambda d: d["kind"] == "player_offline")
    assert offline == {"kind": "player_offline", "playerId": ann.player_id, "nickname": "Ann"}
    back = await rejoin(connect, code, "Ann", token)
    online = await host.wait_push("room:event", lambda d: d["kind"] == "player_online")
    assert online["playerId"] == ann.player_id
    back_online = lambda d: len(d["players"]) > 1 and d["players"][1]["online"]  # noqa: E731
    state = await host.wait_push("room:state", back_online)
    assert state["players"][1]["offlineSince"] is None
    await back.drain()
    assert not events(back, "player_offline")  # never replayed on reconnect


async def test_leaving_sends_player_left_not_an_offline_notice(connect, manager):
    manager.offline_notice_ms = 50
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"))
    assert (await ann.request("room:leave"))["ok"]
    left = await host.wait_push("room:event", lambda d: d["kind"] == "player_left")
    assert left["playerId"] == ann.player_id
    await asyncio.sleep(0.1)
    await host.drain()
    assert not events(host, "player_offline")


async def test_offline_host_transfer_is_announced(connect, manager):
    manager.host_transfer_ms = 50
    code, (host, ann) = await setup_room(connect)
    await host.close()
    changed = await ann.wait_push("room:event", lambda d: d["kind"] == "host_changed")
    assert changed["playerId"] == ann.player_id
    assert changed["data"] == {"previousHostId": host.player_id}
