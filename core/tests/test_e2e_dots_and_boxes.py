"""End to end: a full Dots and Boxes game (4x4, 2 players) over /ws/."""

from games.dots_and_boxes import all_lines
from rooms.validation import RateLimiter
from tests.conftest import make_profile


async def test_dots_and_boxes_end_to_end(connect, monkeypatch):
    monkeypatch.setattr(RateLimiter, "allow", lambda self: True)  # fast scripted play
    host = await connect()
    ack = await host.request("room:create", {"profile": make_profile("Host")})
    code = ack["data"]["room"]["code"]
    guest = await connect()
    assert (await guest.request("room:join", {"code": code, "profile": make_profile("Ann")}))["ok"]
    by_id = {host.player_id: host, guest.player_id: guest}

    ack = await host.request(
        "room:selectGame", {"gameId": "dots_and_boxes", "settings": {"size": 4}}
    )
    assert ack["ok"]
    assert (await host.request("game:start"))["ok"]

    lines = all_lines(4)
    for drawn in range(len(lines)):
        data = await host.wait_push("game:view", lambda d, k=drawn: len(d["view"]["lines"]) == k)
        view = data["view"]
        assert data["gameId"] == "dots_and_boxes" and view["phase"] == "playing"
        current = by_id[view["currentPlayerId"]]
        other = guest if current is host else host
        line = next(line for line in lines if line not in view["lines"])
        if drawn == 0:
            wrong = await other.request("game:action", {"type": "drawLine", "id": line})
            assert not wrong["ok"] and wrong["error"]["code"] == "NOT_YOUR_TURN"
        ack = await current.request("game:action", {"type": "drawLine", "id": line})
        assert ack["ok"], ack

    final = await host.wait_push("game:view", lambda d: d["view"]["phase"] == "done")
    scores = final["view"]["scores"]
    assert sum(scores.values()) == 16
    done = await host.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    results = {r["playerId"]: r for r in done["data"]["results"]}
    assert {pid: r["score"] for pid, r in results.items()} == scores
    best = max(scores.values())
    assert {pid for pid, r in results.items() if r["placement"] == 1} == {
        pid for pid, s in scores.items() if s == best
    }
    room = await host.wait_push("room:state", lambda d: d["status"] == "finished")
    tied = len([s for s in scores.values() if s == best]) == 2
    assert room["scoreboard"] == {
        pid: 50 if tied else (100 if s == best else 0) for pid, s in scores.items()
    }
    assert room["wins"] == {pid: 1 for pid, s in scores.items() if s == best}
