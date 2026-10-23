"""End to end: full Rock-Paper-Scissors games (duel and bracket) over /ws/."""

import asyncio
import json

from games import rps as rps_module
from rooms.validation import RateLimiter
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
    assert results[host.player_id]["points"] == 100 and results[ann.player_id]["points"] == 0
    state = await host.wait_push("room:state", lambda d: d["status"] == "finished")
    assert state["wins"] == {host.player_id: 1}


async def test_rps_duel_rejected_with_three_players(connect):
    code, (host, *_) = await seat(connect, ["Host", "Ann", "Bob"])
    await host.request("room:selectGame", {"gameId": "rps", "settings": {"mode": "duel"}})
    ack = await host.request("game:start")
    assert ack["error"]["code"] == "INVALID_ACTION"
    assert (await host.request("room:peek", {"code": code}))["data"]["status"] == "lobby"


async def test_rps_bracket_end_to_end_scoreboard(connect, manager, monkeypatch):
    """4 players: champion 100, runner-up 66.67, both losing semifinalists tied 3rd (16.67)."""
    monkeypatch.setattr(rps_module, "RPS_REVEAL_MS", 30)
    monkeypatch.setattr(RateLimiter, "allow", lambda self: True)
    code, clients = await seat(connect, ["Host", "Ann", "Bob", "Cat"])
    by_id = {c.player_id: c for c in clients}
    settings = {"mode": "bracket", "bestOf": 3}
    assert (await clients[0].request("room:selectGame", {"gameId": "rps", "settings": settings}))[
        "ok"
    ]
    assert (await clients[0].request("game:start"))["ok"]
    room = manager.rooms[code]
    for _ in range(400):  # the first-listed player of each match always wins
        if room.status != "playing":
            break
        for match in list(room.game_state.matches):
            if match.phase == "picking" and match.b is not None:
                for pid, choice in ((match.a, "rock"), (match.b, "scissors")):
                    if match.picks.get(pid) is None:
                        await by_id[pid].request("game:action", {"type": "pick", "choice": choice})
        await asyncio.sleep(0.01)
    done = await clients[0].wait_push("game:event", lambda d: d["kind"] == "gameOver")
    placements = sorted(r["placement"] for r in done["data"]["results"])
    points = sorted((r["points"] for r in done["data"]["results"]), reverse=True)
    assert placements == [1, 2, 3, 3] and points == [100, 66.67, 16.67, 16.67]
    state = await clients[0].wait_push("room:state", lambda d: d["status"] == "finished")
    assert sorted(state["scoreboard"].values(), reverse=True) == [100, 66.67, 16.67, 16.67]
    champion = next(r["playerId"] for r in done["data"]["results"] if r["placement"] == 1)
    assert state["wins"] == {champion: 1}
