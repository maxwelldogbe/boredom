"""Integration: every real game forfeits the same way through game:quit, room:leave and the
offline timeout, and ends at once when one player is left."""

import pytest

from games import registry
from tests.conftest import make_profile

GAMES = ["rps", "guess_race", "hangman"]
SETTINGS = {"rps": {"mode": "bracket"}}
NAMES = ("Host", "Ann", "Bob", "Cat")


async def seat(connect, game_id, count):
    host = await connect()
    ack = await host.request("room:create", {"profile": make_profile(NAMES[0])})
    code = ack["data"]["room"]["code"]
    clients = [host]
    for name in NAMES[1:count]:
        client = await connect()
        assert (await client.request("room:join", {"code": code, "profile": make_profile(name)}))[
            "ok"
        ]
        clients.append(client)
    select = {"gameId": game_id, "settings": SETTINGS.get(game_id, {})}
    assert (await host.request("room:selectGame", select))["ok"]
    assert (await host.request("game:start"))["ok"]
    for client in clients:
        await client.wait_push("game:view")
    return code, clients


async def forfeit(client, how):
    if how == "quit":
        assert (await client.request("game:quit"))["ok"]
    elif how == "leave":
        assert (await client.request("room:leave"))["ok"]
    else:
        await client.close()


@pytest.mark.parametrize("how", ["quit", "leave", "offline"])
@pytest.mark.parametrize("game_id", GAMES)
async def test_last_player_standing_wins_at_once(connect, manager, game_id, how):
    manager.offline_forfeit_ms = 50
    count = max(2, registry.get_game(game_id).min_players)
    code, clients = await seat(connect, game_id, count)
    host, rest = clients[0], clients[1:]
    for client in rest[:-1]:
        assert (await client.request("game:quit"))["ok"]
    await forfeit(rest[-1], how)
    over = await host.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    state = await host.wait_push("room:state", lambda d: d["status"] == "finished")
    places = {r["playerId"]: r["placement"] for r in over["data"]["results"]}
    assert places[host.player_id] == 1
    assert places[rest[-1].player_id] == 2  # the latest forfeiter ranks highest of them
    assert state["endReason"] == "forfeit" and state["wins"] == {host.player_id: 1}


@pytest.mark.parametrize("game_id", GAMES)
async def test_three_player_game_continues_after_one_quits(connect, manager, game_id):
    code, (host, ann, bob) = await seat(connect, game_id, 3)
    assert (await bob.request("game:quit"))["ok"]
    out = lambda d: len(d["players"]) > 2 and not d["players"][2]["inGame"]  # noqa: E731
    state = await host.wait_push("room:state", out)
    assert state["status"] == "playing" and manager.rooms[code].status == "playing"
    ack = await bob.request("game:action", {"type": "noop"})
    assert ack["error"]["code"] == "INVALID_ACTION"
