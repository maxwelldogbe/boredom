"""End to end: a full Liar's Dice game (2 players, 3 dice each) over /ws/."""

from games import liars_dice as ld_module
from rooms.validation import RateLimiter
from tests.conftest import make_profile


async def test_liars_dice_end_to_end(connect, monkeypatch):
    monkeypatch.setattr(ld_module, "DICE_REVEAL_MS", 30)
    monkeypatch.setattr(RateLimiter, "allow", lambda self: True)  # fast scripted play
    host = await connect()
    ack = await host.request("room:create", {"profile": make_profile("Host")})
    code = ack["data"]["room"]["code"]
    guest = await connect()
    assert (await guest.request("room:join", {"code": code, "profile": make_profile("Ann")}))["ok"]
    by_id = {host.player_id: host, guest.player_id: guest}
    settings = {"startingDice": 3}
    ack = await host.request("room:selectGame", {"gameId": "liars_dice", "settings": settings})
    assert ack["ok"]
    assert (await host.request("game:start"))["ok"]

    for round_no in range(1, 20):
        views = {}
        for client in (host, guest):
            data = await client.wait_push(
                "game:view",
                lambda d, r=round_no: d["view"]["round"] == r and d["view"]["phase"] == "bidding",
            )
            views[client.player_id] = data["view"]
        for pid, view in views.items():
            assert view["lastReveal"] is None and len(view["myDice"]) == view["diceCounts"][pid]
        starter = views[host.player_id]["currentPlayerId"]
        caller = next(pid for pid in by_id if pid != starter)
        total = views[host.player_id]["totalDice"]
        # An all-sixes bid is almost surely false, so the starter keeps losing dice.
        action = {"type": "bid", "quantity": total, "face": 6}
        ack = await by_id[starter].request("game:action", action)
        assert ack["ok"], ack
        ack = await by_id[caller].request("game:action", {"type": "callLiar"})
        assert ack["ok"], ack
        reveal = await host.wait_push(
            "game:event", lambda d, r=round_no: d["kind"] == "reveal" and d["data"]["round"] == r
        )
        data = reveal["data"]
        assert set(data["dice"]) == set(by_id) and data["callerId"] == caller
        assert data["dice"][host.player_id] == views[host.player_id]["myDice"]
        if data["eliminatedId"]:
            break

    done = await host.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    results = {r["playerId"]: r for r in done["data"]["results"]}
    loser = data["eliminatedId"]
    winner = next(pid for pid in by_id if pid != loser)
    assert results[winner]["placement"] == 1 and results[loser]["placement"] == 2
    room = await host.wait_push("room:state", lambda d: d["status"] == "finished")
    assert room["wins"] == {winner: 1}
    assert room["scoreboard"] == {winner: 100, loser: 0}
