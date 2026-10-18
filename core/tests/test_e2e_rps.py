"""End to end: a full Rock-Paper-Scissors duel over /ws/."""

import json

from games import rps as rps_module
from tests.conftest import make_profile


async def seat(connect, names):
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
    return code, clients


async def test_rps_duel_end_to_end(connect, monkeypatch):
    monkeypatch.setattr(rps_module, "RPS_REVEAL_MS", 50)
    code, (host, ann) = await seat(connect, ["Host", "Ann"])
    ack = await host.request("room:selectGame", {"gameId": "rps", "settings": {"bestOf": 3}})
    assert ack["ok"]
    assert (await host.request("game:start"))["ok"]
    view = (await ann.wait_push("game:view"))["view"]
    assert view["phase"] == "picking" and view["mode"] == "duel"

    for round_no in (1, 2):
        if round_no == 2:  # the reveal pause ends and a new picking round begins
            await ann.wait_push(
                "game:view",
                lambda d, r=round_no: (
                    d["view"]["phase"] == "picking" and d["view"]["matches"][0]["round"] == r
                ),
            )
        await ann.drain()
        ann.pushes.clear()
        choice = "paper" if round_no == 1 else "scissors"
        assert (await host.request("game:action", {"type": "pick", "choice": choice}))["ok"]
        hidden = await ann.wait_push(
            "game:view", lambda d: d["view"]["matches"][0]["hasPicked"][host.player_id]
        )
        assert hidden["view"]["myPick"] is None
        if round_no == 1:
            assert choice not in json.dumps(hidden)
        else:
            assert hidden["view"]["matches"][0]["lastReveal"]["round"] == 1
            assert "scissors" not in json.dumps(hidden)
        answer = "rock" if round_no == 1 else "paper"
        assert (await ann.request("game:action", {"type": "pick", "choice": answer}))["ok"]
        reveal = await ann.wait_push("game:event", lambda d: d["kind"] == "reveal")
        assert reveal["data"]["roundWinner"] == host.player_id

    over = await ann.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    results = {r["playerId"]: r for r in over["data"]["results"]}
    assert results[host.player_id]["points"] == 3 and results[ann.player_id]["points"] == 2
    state = await host.wait_push("room:state", lambda d: d["status"] == "finished")
    assert state["wins"] == {host.player_id: 1}


async def test_rps_duel_rejected_with_three_players(connect):
    code, (host, *_) = await seat(connect, ["Host", "Ann", "Bob"])
    await host.request("room:selectGame", {"gameId": "rps", "settings": {"mode": "duel"}})
    ack = await host.request("game:start")
    assert ack["error"]["code"] == "INVALID_ACTION"
    assert (await host.request("room:peek", {"code": code}))["data"]["status"] == "lobby"
