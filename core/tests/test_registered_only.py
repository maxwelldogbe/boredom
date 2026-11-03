"""Registered-only games (REGISTERED_ONLY_GAMES): guests can neither pick, start nor see them."""

import json

import pytest

from games.constants import REGISTERED_ONLY_GAMES
from tests.conftest import make_profile
from tests.test_accounts_ws import make_account
from tests.test_guest_quota import plays

pytestmark = pytest.mark.django_db(transaction=True)

GAME = "tic_tac_toe"


async def registered(connect, username, nickname):
    _, token = await make_account(username, nickname)
    return await connect(), token


async def room(connect, host_token=None, guests=(), members=()):
    """A room; the host is registered when `host_token` is given. Returns (code, host, clients)."""
    host = await connect()
    payload = {"authToken": host_token} if host_token else {"profile": make_profile("Gus")}
    created = await host.request("room:create", payload)
    assert created["ok"], created
    code = created["data"]["room"]["code"]
    joined = {}
    for client, token in members:
        assert (await client.request("room:join", {"code": code, "authToken": token}))["ok"]
        joined[client.player_id] = client
    for nickname in guests:
        client = await connect()
        ack = await client.request("room:join", {"code": code, "profile": make_profile(nickname)})
        assert ack["ok"], ack
        joined[client.player_id] = client
    return code, host, list(joined.values())


async def test_the_list_is_the_four_new_games() -> None:
    assert REGISTERED_ONLY_GAMES == {"tic_tac_toe", "connect_four", "checkers", "penalty_kick"}


async def test_guest_host_cannot_select_or_start(connect, manager) -> None:
    code, host, _ = await room(connect, guests=["Ann"])
    for game in REGISTERED_ONLY_GAMES:
        ack = await host.request("room:selectGame", {"gameId": game, "settings": {}})
        assert ack["error"]["code"] == "REGISTERED_ONLY"
    assert manager.rooms[code].selected_game is None
    manager.rooms[code].selected_game, manager.rooms[code].settings = GAME, {"bestOf": 1}
    assert (await host.request("game:start"))["error"]["code"] == "REGISTERED_ONLY"
    assert manager.rooms[code].status == "lobby"


async def test_registered_host_can_select_and_start(connect, manager) -> None:
    host_token = (await make_account("reg_host", "Rita"))[1]
    bob, bob_token = await registered(connect, "reg_bob", "Bob")
    code, host, _ = await room(connect, host_token, members=[(bob, bob_token)])
    assert (await host.request("room:selectGame", {"gameId": GAME, "settings": {}}))["ok"]
    assert (await host.request("game:start"))["ok"]
    assert manager.rooms[code].status == "playing"
    assert (await bob.wait_push("game:view"))["gameId"] == GAME


async def test_mixed_room_plays_without_the_guest(connect, manager) -> None:
    host_token = (await make_account("reg_host", "Rita"))[1]
    bob, bob_token = await registered(connect, "reg_bob", "Bob")
    members = [(bob, bob_token)]
    code, host, [_, ann] = await room(connect, host_token, guests=["Ann"], members=members)
    assert (await host.request("room:selectGame", {"gameId": GAME, "settings": {}}))["ok"]
    assert (await host.request("game:start"))["ok"]
    r = manager.rooms[code]
    assert r.game_players == [host.player_id, bob.player_id]
    assert r.player(ann.player_id).in_game is False
    assert await plays() == {}  # the free-games counter is untouched
    await bob.wait_push("game:view")
    await ann.drain()
    assert all(p["type"] != "game:view" for p in ann.pushes)
    watch = await ann.request("game:action", {"type": "watch", "matchId": "r1m1"})
    assert watch["error"]["code"] == "REGISTERED_ONLY"
    assert GAME not in json.dumps(ann.pushes)


async def test_start_rejected_below_min_players_lists_the_guests(connect, manager) -> None:
    host_token = (await make_account("reg_host", "Rita"))[1]
    code, host, _ = await room(connect, host_token, guests=["Ann", "Cat"])
    assert (await host.request("room:selectGame", {"gameId": GAME, "settings": {}}))["ok"]
    ack = await host.request("game:start")
    assert ack["error"]["code"] == "REGISTERED_ONLY"
    assert ack["error"]["data"] == {"nicknames": ["Ann", "Cat"]}
    r = manager.rooms[code]
    assert r.status == "lobby" and r.selected_game == GAME
    assert all(p.in_game for p in r.players)


async def test_guests_never_get_the_game_id_and_ready_counts_skip_them(connect) -> None:
    host_token = (await make_account("reg_host", "Rita"))[1]
    bob, bob_token = await registered(connect, "reg_bob", "Bob")
    members = [(bob, bob_token)]
    code, host, [_, ann] = await room(connect, host_token, guests=["Ann"], members=members)
    assert (await host.request("room:selectGame", {"gameId": GAME, "settings": {}}))["ok"]
    seen = await ann.wait_push("room:state", lambda d: d["readyCheck"] is not None)
    assert seen["selectedGame"] is None and seen["settings"] is None
    blocked = {p["id"]: p["registeredOnlyBlocked"] for p in seen["players"]}
    assert blocked == {host.player_id: False, bob.player_id: False, ann.player_id: True}
    assert seen["readyCheck"] == {"count": 0, "total": 1}  # only Bob counts
    mine = await bob.wait_push("room:state", lambda d: d["selectedGame"] == GAME)
    assert mine["settings"] == {"bestOf": 3}
    late = await connect()
    ack = await late.request("room:join", {"code": code, "profile": make_profile("Cat")})
    assert ack["ok"] and ack["data"]["room"]["selectedGame"] is None
    await ann.drain()
    assert GAME not in json.dumps(ann.pushes) + json.dumps(ack)


async def test_host_passing_to_a_guest_clears_the_selection(connect, manager) -> None:
    host_token = (await make_account("reg_host", "Rita"))[1]
    code, host, [ann] = await room(connect, host_token, guests=["Ann"])
    assert (await host.request("room:selectGame", {"gameId": GAME, "settings": {}}))["ok"]
    assert (await host.request("room:leave"))["ok"]
    event = await ann.wait_push("room:event", lambda d: d["kind"] == "game_unselected")
    assert event["data"] == {"reason": "registered_only"} and event["playerId"] == ann.player_id
    r = manager.rooms[code]
    assert r.host_id == ann.player_id and r.selected_game is None
    state = await ann.wait_push("room:state", lambda d: d["hostId"] == ann.player_id)
    assert state["players"][0]["registeredOnlyBlocked"] is False


async def test_open_games_are_unchanged_for_guests(connect, manager) -> None:
    code, host, [ann] = await room(connect, guests=["Ann"])
    assert (await host.request("room:selectGame", {"gameId": "rps", "settings": {}}))["ok"]
    state = await ann.wait_push("room:state", lambda d: d["selectedGame"] == "rps")
    assert not any(p["registeredOnlyBlocked"] for p in state["players"])
    assert state["readyCheck"] == {"count": 0, "total": 1}
    assert (await host.request("game:start"))["ok"]
    assert (await ann.wait_push("game:view"))["gameId"] == "rps"
