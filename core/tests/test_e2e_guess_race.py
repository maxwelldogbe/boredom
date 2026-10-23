"""End to end: a full Guess Race game over /ws/."""

import json

from games import guess_race as gr_module
from rooms.validation import RateLimiter
from tests.conftest import make_profile


async def test_guess_race_end_to_end(connect, manager, monkeypatch):
    monkeypatch.setattr(gr_module, "GUESS_REVEAL_MS", 30)
    # Rounds are squeezed into milliseconds here; rate limiting has its own test.
    monkeypatch.setattr(RateLimiter, "allow", lambda self: True)
    host = await connect()
    code = (await host.request("room:create", {"profile": make_profile("Host")}))["data"]["room"][
        "code"
    ]
    ann = await connect()
    assert (await ann.request("room:join", {"code": code, "profile": make_profile("Ann")}))["ok"]
    settings = {"content": "mixed", "rounds": 5}
    assert (await host.request("room:selectGame", {"gameId": "guess_race", "settings": settings}))[
        "ok"
    ]
    assert (await host.request("game:start"))["ok"]

    for round_no in range(1, 6):
        view = await ann.wait_push(
            "game:view",
            lambda d, r=round_no: d["view"]["round"] == r and d["view"]["phase"] == "guessing",
        )
        answer = manager.rooms[code].game_state.current.answer
        assert answer.lower() not in json.dumps(view, ensure_ascii=False).lower()
        wrong = await ann.request("game:action", {"type": "guess", "text": "zzz nope"})
        assert wrong["ok"]
        first, second = (host, ann) if round_no % 2 else (ann, host)
        assert (await first.request("game:action", {"type": "guess", "text": answer}))["ok"]
        solved = await second.wait_push(
            "game:view", lambda d, r=round_no: d["view"]["round"] == r and d["view"]["solvers"]
        )
        assert answer.lower() not in json.dumps(solved, ensure_ascii=False).lower()
        # Both players solve, so the round ends at once, without waiting for the timer.
        assert (await second.request("game:action", {"type": "guess", "text": answer}))["ok"]
        over = await ann.wait_push("game:event", lambda d: d["kind"] == "roundOver")
        assert over["data"]["answer"] == answer
        assert over["data"]["solvers"] == [
            {"playerId": first.player_id, "rank": 1, "points": 100},
            {"playerId": second.player_id, "rank": 2, "points": 80},
        ]

    done = await host.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    results = {r["playerId"]: r for r in done["data"]["results"]}
    assert results[host.player_id]["placement"] == 1
    assert results[host.player_id]["score"] == 3 * 100 + 2 * 80
    assert results[ann.player_id]["score"] == 2 * 100 + 3 * 80
    assert results[host.player_id]["points"] == 100 and results[ann.player_id]["points"] == 0
    state = await ann.wait_push("room:state", lambda d: d["status"] == "finished")
    assert state["scoreboard"] == {host.player_id: 100, ann.player_id: 0}
    assert state["wins"] == {host.player_id: 1}
