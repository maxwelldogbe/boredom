"""End to end: a full Hangman game (group mode, 3 players) over /ws/, with an upheld flag."""

import json

from games import hangman as hm_module
from rooms.validation import RateLimiter
from tests.conftest import make_profile


async def test_hangman_end_to_end(connect, monkeypatch):
    monkeypatch.setattr(hm_module, "HANGMAN_REVEAL_MS", 30)
    monkeypatch.setattr(hm_module, "HANGMAN_FLAG_WINDOW_MS", 300)
    monkeypatch.setattr(RateLimiter, "allow", lambda self: True)  # fast scripted play
    host = await connect()
    ack = await host.request("room:create", {"profile": make_profile("Host")})
    code = ack["data"]["room"]["code"]
    clients = [host]
    for name in ("Ann", "Bob"):
        client = await connect()
        assert (await client.request("room:join", {"code": code, "profile": make_profile(name)}))[
            "ok"
        ]
        clients.append(client)
    host_, ann, bob = clients
    ack = await host.request("room:selectGame", {"gameId": "hangman", "settings": {}})
    assert ack["ok"]
    assert (await host.request("game:start"))["ok"]

    plans = [("ZEBRA", 0), ("QUIZZES", 2), ("JAZZY", 6)]  # (word, wrong letters)
    for round_no, setter in enumerate(clients, start=1):
        guessers = [c for c in clients if c is not setter]
        view = await setter.wait_push(
            "game:view",
            lambda d, r=round_no: d["view"]["round"] == r and d["view"]["phase"] == "setting",
        )
        assert view["view"]["isSetter"]
        word, wrong = plans[round_no - 1]
        too_short = await setter.request("game:action", {"type": "setWord", "word": "quiz"})
        assert too_short["error"]["code"] == "INVALID_ACTION"
        ack = await setter.request(
            "game:action", {"type": "setWord", "word": word.lower(), "hint": "Try it"}
        )
        assert ack["ok"]

        def in_round(d, r=round_no):
            return d["view"]["round"] == r and d["view"]["phase"] == "guessing"

        seen = await guessers[0].wait_push("game:view", in_round)
        assert word not in json.dumps(seen) and seen["view"]["mask"] == [None] * len(word)
        misses = [ch for ch in "BCDFGH" if ch not in word][:wrong]
        letters = misses if wrong >= 6 else [*misses, *dict.fromkeys(word)]
        for i, letter in enumerate(letters):
            ack = await guessers[i % 2].request(
                "game:action", {"type": "guessLetter", "letter": letter}
            )
            assert ack["ok"]
        over = await guessers[1].wait_push(
            "game:event",
            lambda d, r=round_no: d["kind"] == "roundOver" and d["data"]["round"] == r,
        )
        assert over["data"]["word"] == word
        assert sum(over["data"]["award"].values()) == 12
        if round_no == 2:  # Bob flags Ann's word; Host agrees it is not a real word
            assert (await bob.request("game:action", {"type": "flagWord"}))["ok"]
            vote = await host_.wait_push("game:view", lambda d: d["view"]["phase"] == "flagVote")
            assert vote["view"]["flag"]["canVote"] and "votes" not in json.dumps(vote)
            ack = await host_.request("game:action", {"type": "voteWord", "valid": False})
            assert ack["ok"]
            result = await ann.wait_push("game:event", lambda d: d["kind"] == "flagResult")
            assert result["data"]["upheld"] is True
            assert result["data"]["award"] == {
                ann.player_id: 0, host_.player_id: 6, bob.player_id: 6
            }

    done = await host.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    results = {r["playerId"]: r for r in done["data"]["results"]}
    # Host 0+6+0, Ann 6+0+0, Bob 6+6+12: Bob wins, Host and Ann tie for 2nd of 3.
    assert {pid: r["score"] for pid, r in results.items()} == {
        host_.player_id: 6, ann.player_id: 6, bob.player_id: 24
    }
    assert {pid: r["placement"] for pid, r in results.items()} == {
        host_.player_id: 2, ann.player_id: 2, bob.player_id: 1
    }
    state = await host.wait_push("room:state", lambda d: d["status"] == "finished")
    assert state["scoreboard"] == {host_.player_id: 25, ann.player_id: 25, bob.player_id: 100}
    assert state["wins"] == {bob.player_id: 1}
