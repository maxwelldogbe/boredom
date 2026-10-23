"""End to end: a full Name It Survival game (3 players, with a challenge) over /ws/."""

from rooms.validation import RateLimiter
from tests.conftest import make_profile


async def test_name_it_end_to_end(connect, monkeypatch):
    monkeypatch.setattr(RateLimiter, "allow", lambda self: True)  # fast scripted play
    a = await connect()
    ack = await a.request("room:create", {"profile": make_profile("Host")})
    code = ack["data"]["room"]["code"]
    b, c = await connect(), await connect()
    for client, name in ((b, "Ann"), (c, "Bob")):
        ack = await client.request("room:join", {"code": code, "profile": make_profile(name)})
        assert ack["ok"]
    assert (await a.request("room:selectGame", {"gameId": "name_it", "settings": {}}))["ok"]
    assert (await a.request("game:start"))["ok"]

    view = (await a.wait_push("game:view", lambda d: d["view"]["phase"] == "topicSelect"))["view"]
    assert view["isTopicChooser"] and len(view["suggestions"]) == 5
    first = view["suggestions"][0]
    wrong = await b.request("game:action", {"type": "chooseTopic", "topic": first})
    assert wrong["error"]["code"] == "NOT_YOUR_TURN"
    typed = await a.request("game:action", {"type": "chooseTopic", "topic": "My own topic"})
    assert typed["error"]["code"] == "INVALID_ACTION"  # allowCustomTopics is off by default
    assert (await a.request("game:action", {"type": "chooseTopic", "topic": first}))["ok"]
    assert (await a.request("game:action", {"type": "submitAnswer", "text": "Apple"}))["ok"]
    assert (await b.request("game:action", {"type": "submitAnswer", "text": "Car"}))["ok"]

    # Bob challenges Ann's answer; Host is the only voter and votes Invalid.
    assert (await c.request("game:action", {"type": "challenge"}))["ok"]
    voting = await a.wait_push("game:view", lambda d: d["view"]["phase"] == "challenge")
    assert voting["view"]["challenge"]["canVote"] and voting["view"]["challenge"]["text"] == "Car"
    assert (await a.request("game:action", {"type": "vote", "valid": False}))["ok"]
    result = await c.wait_push("game:event", lambda d: d["kind"] == "challengeResult")
    assert result["data"]["valid"] is False and result["data"]["votes"] == {a.player_id: False}
    out = await c.wait_push("game:event", lambda d: d["kind"] == "eliminated")
    assert out["data"]["playerId"] == b.player_id and out["data"]["reason"] == "challenge"

    # Ann (out) picks the next topic; Bob, after her in seat order, starts.
    view = (await b.wait_push("game:view", lambda d: d["view"]["isTopicChooser"]))["view"]
    ack = await b.request("game:action", {"type": "chooseTopic", "topic": view["suggestions"][0]})
    assert ack["ok"]
    assert (await c.request("game:action", {"type": "submitAnswer", "text": "Blue"}))["ok"]
    assert (await a.request("game:action", {"type": "submitAnswer", "text": " the blue!"}))["ok"]
    out = await c.wait_push(
        "game:event", lambda d: d["kind"] == "eliminated" and d["data"]["reason"] == "duplicate"
    )
    assert out["data"]["playerId"] == a.player_id

    done = await a.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    placements = {r["playerId"]: r["placement"] for r in done["data"]["results"]}
    assert placements == {c.player_id: 1, a.player_id: 2, b.player_id: 3}
    room = await a.wait_push("room:state", lambda d: d["status"] == "finished")
    assert room["wins"] == {c.player_id: 1}
    assert room["scoreboard"] == {c.player_id: 100, a.player_id: 50, b.player_id: 0}
