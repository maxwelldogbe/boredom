"""End to end: a 3-player tic-tac-toe bracket over /ws/ ends with the session scoreboard."""

import asyncio

import pytest

from rooms.validation import RateLimiter
from tests.test_e2e_series_games import seat

pytestmark = pytest.mark.django_db(transaction=True)

WIN = [0, 3, 1, 4, 2]  # the first mover takes the top row


async def test_tic_tac_toe_bracket_end_to_end_scoreboard(connect, manager, monkeypatch):
    """Champion 100, runner-up 50, third 0."""
    monkeypatch.setattr(RateLimiter, "allow", lambda self: True)
    code, clients = await seat(connect, ["Host", "Ann", "Bob"])
    by_id = {c.player_id: c for c in clients}
    ack = await clients[0].request(
        "room:selectGame", {"gameId": "tic_tac_toe", "settings": {"bestOf": 1}}
    )
    assert ack["ok"]
    assert (await clients[0].request("game:start"))["ok"]
    room = manager.rooms[code]
    for _ in range(100):
        if room.status != "playing":
            break
        match_id = next(m.id for m in room.game_state.matches if m.winner is None)
        for cell in WIN:  # the room swaps in a fresh state copy after every action
            match = next(m for m in room.game_state.matches if m.id == match_id)
            mover = by_id[match.game.turn]
            assert (await mover.request("game:action", {"type": "place", "cell": cell}))["ok"]
        await asyncio.sleep(0.01)
    done = await clients[0].wait_push("game:event", lambda d: d["kind"] == "gameOver")
    results = sorted(done["data"]["results"], key=lambda r: r["placement"])
    assert [r["placement"] for r in results] == [1, 2, 3]
    assert [r["points"] for r in results] == [100, 50, 0]
    state = await clients[0].wait_push("room:state", lambda d: d["status"] == "finished")
    assert state["scoreboard"] == {r["playerId"]: r["points"] for r in results}
    assert state["wins"] == {results[0]["playerId"]: 1}
