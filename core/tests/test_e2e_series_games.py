"""End to end: full Connect Four and penalty kick games over /ws/ end with the scoreboard."""

import pytest

from games import penalty_kick
from rooms.validation import RateLimiter
from tests.test_accounts_ws import make_account

pytestmark = pytest.mark.django_db(transaction=True)


async def seat(connect, names):
    """Registered accounts only: these games are registered-only (PROTOCOL.md 12)."""
    clients, code = [], None
    for i, name in enumerate(names):
        _, token = await make_account(f"user_{name.lower()}", name)
        client = await connect()
        if code is None:
            ack = await client.request("room:create", {"authToken": token})
            code = ack["data"]["room"]["code"]
        else:
            ack = await client.request("room:join", {"code": code, "authToken": token})
        assert ack["ok"], (i, ack)
        clients.append(client)
    return code, clients


async def start(clients, game_id, settings):
    ack = await clients[0].request("room:selectGame", {"gameId": game_id, "settings": settings})
    assert ack["ok"]
    assert (await clients[0].request("game:start"))["ok"]


async def assert_won(winner, loser):
    done = await winner.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    points = {r["playerId"]: r["points"] for r in done["data"]["results"]}
    assert points == {winner.player_id: 100, loser.player_id: 0}
    state = await winner.wait_push("room:state", lambda d: d["status"] == "finished")
    assert state["scoreboard"] == points and state["wins"] == {winner.player_id: 1}


async def test_connect_four_end_to_end_scoreboard(connect, manager, monkeypatch):
    monkeypatch.setattr(RateLimiter, "allow", lambda self: True)
    code, (host, ann) = await seat(connect, ["Host", "Ann"])
    by_id = {host.player_id: host, ann.player_id: ann}
    await start([host, ann], "connect_four", {"bestOf": 1})
    room = manager.rooms[code]
    opener = room.game_state.matches[0].game.turn
    for col in [0, 1, 0, 1, 0, 1, 0]:  # the opener stacks four in column 0
        mover = by_id[room.game_state.matches[0].game.turn]
        assert (await mover.request("game:action", {"type": "drop", "column": col}))["ok"]
    winner = by_id[opener]
    await assert_won(winner, ann if winner is host else host)


async def test_penalty_kick_end_to_end_scoreboard(connect, manager, monkeypatch):
    """Host shoots into the corner, Ann shoots wide: 2-0 after four kicks ends a 3-kick shootout."""
    monkeypatch.setattr(RateLimiter, "allow", lambda self: True)
    fast = {"FLIGHT_MS_MAX": 20, "FLIGHT_MS_MIN": 10, "DIVE_GRACE_MS": 0, "RESULT_MS": 20}
    for name, ms in fast.items():
        monkeypatch.setattr(penalty_kick, f"PENALTY_{name}", ms)
    monkeypatch.setattr(penalty_kick, "keeper_path", lambda start, speed, rng: [])  # stays home
    code, (host, ann) = await seat(connect, ["Host", "Ann"])
    by_id = {host.player_id: host, ann.player_id: ann}
    await start([host, ann], "penalty_kick", {"kicksPerPlayer": 3})
    for n in range(1, 5):

        def aiming(d, n=n):
            game = (d["view"]["match"] or {}).get("game") or {}
            return game.get("phase") == "aiming" and game.get("kickNo") == n

        game = (await host.wait_push("game:view", aiming))["view"]["match"]["game"]
        shooter = by_id[game["shooter"]]
        aim = {"x": 0.2, "y": 0.15} if shooter is host else {"x": -0.4, "y": 0.5}
        shot = {"type": "shoot", "aim": aim, "power": 0.5}
        assert (await shooter.request("game:action", shot))["ok"]
    await assert_won(host, ann)
