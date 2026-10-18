"""Integration: reconnects, mid-game rules, host transfer, cleanup, rate limit, full game loop."""

import asyncio
import json

from games.constants import ACTION_RATE_LIMIT_PER_SEC
from rooms import hooks
from tests.conftest import make_profile
from tests.dummy_game import SECRET


def offline_at(index):
    """Predicate: the room:state shows the seat at `index` offline."""
    return lambda d: len(d["players"]) > index and not d["players"][index]["online"]


async def setup_room(connect, names=("Host", "Ann"), settings=None):
    """Create a room, seat everyone, select the dummy game. Returns the clients."""
    host = await connect()
    ack = await host.request("room:create", {"profile": make_profile(names[0])})
    code = ack["data"]["room"]["code"]
    clients = [host]
    for name in names[1:]:
        client = await connect()
        assert (await client.request("room:join", {"code": code, "profile": make_profile(name)}))[
            "ok"
        ]
        clients.append(client)
    ack = await host.request("room:selectGame", {"gameId": "dummy", "settings": settings or {}})
    assert ack["ok"], ack
    return code, clients


async def start(clients):
    assert (await clients[0].request("game:start"))["ok"]
    for client in clients:
        await client.wait_push("game:view")


async def test_reconnect_by_token_restores_seat(connect):
    code, (host, ann) = await setup_room(connect)
    pid, token = ann.player_id, ann.token
    await ann.close()
    state = await host.wait_push("room:state", offline_at(1))
    assert state["players"][1]["id"] == pid
    again = await connect()
    ack = await again.request(
        "room:join", {"code": code, "profile": make_profile("Ann"), "roomToken": token}
    )
    assert ack["ok"] and ack["data"]["playerId"] == pid
    state = await host.wait_push(
        "room:state", lambda d: len(d["players"]) > 1 and d["players"][1]["online"]
    )
    assert len(state["players"]) == 2


async def test_wrong_token_takes_a_new_seat_in_lobby(connect):
    code, (host, ann) = await setup_room(connect)
    other = await connect()
    ack = await other.request(
        "room:join", {"code": code, "profile": make_profile("Ann"), "roomToken": "bogus"}
    )
    assert ack["ok"] and ack["data"]["playerId"] != ann.player_id
    assert ack["data"]["room"]["players"][2]["nickname"] == "Ann2"


async def test_reclaiming_from_second_tab_detaches_first(connect):
    code, (host, ann) = await setup_room(connect)
    tab2 = await connect()
    payload = {"code": code, "profile": make_profile("Ann"), "roomToken": ann.token}
    assert (await tab2.request("room:join", payload))["ok"]
    err = await ann.wait_push("error")
    assert err["code"] == "NOT_IN_ROOM"
    assert (await ann.request("game:start"))["error"]["code"] == "NOT_IN_ROOM"


async def test_mid_game_join_rejected_but_token_rejoin_allowed(connect):
    code, (host, ann) = await setup_room(connect)
    await start([host, ann])
    stranger = await connect()
    ack = await stranger.request("room:join", {"code": code, "profile": make_profile("Zed")})
    assert ack["error"]["code"] == "GAME_IN_PROGRESS"
    assert (await stranger.request("room:peek", {"code": code}))["data"]["status"] == "playing"
    token = ann.token
    await ann.close()
    back = await connect()
    payload = {"code": code, "profile": make_profile("Ann"), "roomToken": token}
    assert (await back.request("room:join", payload))["ok"]
    view = await back.wait_push("game:view")
    assert view["gameId"] == "dummy" and "serverNow" in view


async def test_host_transfer_after_offline_timeout(connect, manager):
    manager.host_transfer_ms = 50
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"))
    await host.close()
    state = await ann.wait_push("room:state", lambda d: d["hostId"] == ann.player_id)
    assert state["hostId"] == ann.player_id  # longest-seated online player


async def test_host_keeps_role_if_back_in_time(connect, manager):
    manager.host_transfer_ms = 300
    code, (host, ann) = await setup_room(connect)
    host_id, token = host.player_id, host.token
    await host.close()
    back = await connect()
    payload = {"code": code, "profile": make_profile("Host"), "roomToken": token}
    assert (await back.request("room:join", payload))["ok"]
    await asyncio.sleep(0.4)
    assert manager.rooms[code].host_id == host_id


async def test_idle_and_empty_rooms_are_cleaned_up(connect, manager):
    code, (host, ann) = await setup_room(connect)
    assert await manager.cleanup() == []
    real_clock = manager.clock
    manager.clock = lambda: real_clock() + manager.idle_ttl_ms + 1
    assert await manager.cleanup() == [code]
    assert code not in manager.rooms
    err = await host.wait_push("error")
    assert err["code"] == "NOT_IN_ROOM"
    assert (await ann.request("room:peek", {"code": code}))["data"]["exists"] is False


async def test_cleanup_loop_runs_in_background(connect, manager):
    manager.cleanup_interval_ms = 20
    manager.idle_ttl_ms = 0
    code, _ = await setup_room(connect)
    await asyncio.sleep(0.15)
    assert code not in manager.rooms


async def test_rate_limit(connect):
    code, (host, ann) = await setup_room(connect, settings={"target": 10})
    await start([host, ann])
    codes = []
    for _ in range(ACTION_RATE_LIMIT_PER_SEC + 1):
        codes.append((await ann.request("game:action", {"type": "noop"}))["error"]["code"])
    assert codes == ["INVALID_ACTION"] * ACTION_RATE_LIMIT_PER_SEC + ["RATE_LIMITED"]


async def test_action_errors_change_nothing(connect, manager):
    code, (host, ann) = await setup_room(connect)
    assert (await ann.request("game:action", {"type": "score"}))["error"][
        "code"
    ] == "INVALID_ACTION"
    await start([host, ann])
    before = json.dumps(manager.rooms[code].game_state, sort_keys=True)
    ack = await ann.request("game:action", {"type": "score"})
    assert ack["error"]["code"] == "NOT_YOUR_TURN"
    assert json.dumps(manager.rooms[code].game_state, sort_keys=True) == before
    ack = await host.request("room:selectGame", {"gameId": "dummy", "settings": {}})
    assert ack["error"]["code"] == "GAME_IN_PROGRESS"
    assert (await host.request("game:start"))["error"]["code"] == "GAME_IN_PROGRESS"


async def test_full_game_loop_with_timer_scoreboard_and_hook(connect, manager, monkeypatch):
    finished = []
    monkeypatch.setattr(hooks, "on_game_finished", lambda *args: finished.append(args))
    code, (host, ann) = await setup_room(connect, settings={"target": 2, "turnMs": 150})
    await start([host, ann])

    # Views are personalized: only the first seat sees the dummy secret.
    await host.request("game:action", {"type": "score"})
    host_view = await host.wait_push("game:view")
    ann_view = await ann.wait_push("game:view")
    assert host_view["view"]["secret"] == SECRET
    assert SECRET not in json.dumps(ann_view)
    assert (await ann.wait_push("game:event"))["kind"] == "scored"

    # Ann lets her turn time out: the room timer calls tick.
    timeout = await host.wait_push("game:event", lambda d: d["kind"] == "timeout")
    assert timeout["data"]["playerId"] == ann.player_id

    assert (await host.request("game:action", {"type": "score"}))["ok"]
    over = await ann.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    results = {r["playerId"]: r for r in over["data"]["results"]}
    assert results[host.player_id] == {"playerId": host.player_id, "placement": 1, "points": 2}
    assert results[ann.player_id]["placement"] == 2
    state = await ann.wait_push("room:state", lambda d: d["status"] == "finished")
    assert state["scoreboard"] == {host.player_id: 2, ann.player_id: 0}
    assert state["wins"] == {host.player_id: 1}
    assert finished and finished[0][0] == code and finished[0][2] == "dummy"
    assert manager.rooms[code].timer_task is None

    assert (await ann.request("game:action", {"type": "score"}))["error"][
        "code"
    ] == "INVALID_ACTION"
    assert (await host.request("game:start"))["error"]["code"] == "INVALID_ACTION"
    await ann.drain()
    ann.pushes.clear()
    assert (await host.request("game:playAgain"))["ok"]
    state = await ann.wait_push("room:state", lambda d: d["status"] == "lobby")
    assert state["selectedGame"] == "dummy" and state["scoreboard"][host.player_id] == 2

    # A second game adds to the session scoreboard.
    await host.drain()
    host.pushes.clear()
    await start([host, ann])
    for _ in range(2):
        await host.request("game:action", {"type": "score"})
        await ann.request("game:action", {"type": "score"})
    state = await host.wait_push("room:state", lambda d: d["status"] == "finished")
    assert state["scoreboard"] == {host.player_id: 4, ann.player_id: 1}


async def test_leave_mid_game_keeps_seat_until_game_ends(connect, manager):
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"), {"target": 1})
    await start([host, ann, bob])
    assert (await ann.request("room:leave"))["ok"]
    state = await host.wait_push("room:state", offline_at(1))
    assert len(state["players"]) == 3
    view = await host.wait_push("game:view", lambda d: d["view"]["offline"])
    assert view["view"]["offline"] == [ann.player_id]
    assert (await host.request("game:action", {"type": "score"}))["ok"]
    state = await bob.wait_push("room:state", lambda d: d["status"] == "finished")
    assert [p["nickname"] for p in state["players"]] == ["Host", "Bob"]
    assert ann.player_id not in state["scoreboard"]


async def test_host_leaving_mid_game_transfers_immediately(connect):
    code, (host, ann) = await setup_room(connect)
    await start([host, ann])
    assert (await host.request("room:leave"))["ok"]
    state = await ann.wait_push("room:state", lambda d: d["hostId"] == ann.player_id)
    assert state["status"] == "playing"


async def test_offline_player_at_start_is_reported_to_game(connect, manager):
    code, (host, ann) = await setup_room(connect)
    await ann.close()
    await host.wait_push("room:state", offline_at(1))
    assert (await host.request("game:start"))["ok"]
    view = await host.wait_push("game:view")
    assert view["view"]["offline"] == [ann.player_id]
