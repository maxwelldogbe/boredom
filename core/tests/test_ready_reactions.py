"""Integration: the lobby ready check (room:ready) and emoji reactions (room:react)."""

import pytest

from analytics.recorder import recorder
from games.constants import REACTION_EMOJIS
from tests.conftest import make_profile
from tests.test_quit_end_game import events, rejoin
from tests.test_rooms_lifecycle import offline_at, setup_room, start


def ready_of(state, client):
    return next(p["ready"] for p in state["players"] if p["id"] == client.player_id)


def ready_count(n):
    """Predicate: the room:state's ready check shows `n` ready."""
    return lambda d: d["readyCheck"] is not None and d["readyCheck"]["count"] == n


async def ready(client, value=True):
    return await client.request("room:ready", {"ready": value})


async def latest_state(client):
    await client.drain()
    return client.latest("room:state")


# ----- room:ready --------------------------------------------------------------------------------


async def test_ready_toggles_on_and_off(connect):
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"))
    assert (await ready(ann))["ok"]
    state = await host.wait_push("room:state", ready_count(1))
    assert ready_of(state, ann) is True and ready_of(state, bob) is False
    assert state["readyCheck"] == {"count": 1, "total": 2}
    assert (await ready(ann, False))["ok"]
    state = await host.wait_push("room:state", ready_count(0))
    assert ready_of(state, ann) is False


async def test_ready_check_is_null_without_a_game_and_host_is_never_ready(connect):
    host = await connect()
    ack = await host.request("room:create", {"profile": make_profile("Host")})
    room = ack["data"]["room"]
    assert room["readyCheck"] is None and room["players"][0]["ready"] is False
    ann = await connect()
    await ann.request("room:join", {"code": room["code"], "profile": make_profile("Ann")})
    assert (await ready(ann))["error"]["code"] == "INVALID_ACTION"  # no game selected


async def test_ready_rejections(connect):
    code, (host, ann) = await setup_room(connect)
    assert (await ready(host))["error"]["code"] == "INVALID_ACTION"
    assert (await ann.request("room:ready", {"ready": "yes"}))["error"]["code"] == "INVALID_ACTION"
    assert (await ann.request("room:ready", {}))["error"]["code"] == "INVALID_ACTION"
    stranger = await connect()
    assert (await ready(stranger))["error"]["code"] == "NOT_IN_ROOM"
    await start([host, ann])
    assert (await ready(ann))["error"]["code"] == "INVALID_ACTION"


async def test_ready_is_rejected_in_a_finished_room(connect):
    code, (host, ann) = await setup_room(connect, settings={"target": 1})
    await start([host, ann])
    await host.request("game:action", {"type": "score"})
    await ann.wait_push("room:state", lambda d: d["status"] == "finished")
    assert (await ready(ann))["error"]["code"] == "INVALID_ACTION"


async def test_counts_exclude_offline_players_and_keep_their_flag(connect, manager):
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"))
    await ready(ann)
    await ready(bob)
    await host.wait_push("room:state", ready_count(2))
    await bob.close()
    state = await host.wait_push("room:state", offline_at(2))
    assert state["readyCheck"] == {"count": 1, "total": 1}
    assert state["players"][2]["ready"] is True  # the flag is kept while offline


async def test_reconnecting_seat_keeps_its_flag(connect):
    code, (host, ann) = await setup_room(connect)
    await ready(ann)
    token = ann.token
    await ann.close()
    await host.wait_push("room:state", offline_at(1))
    again = await rejoin(connect, code, "Ann", token)
    state = await latest_state(again)
    assert state["players"][1]["ready"] is True
    assert state["readyCheck"] == {"count": 1, "total": 1}


async def test_a_new_seat_starts_not_ready(connect):
    code, (host, ann) = await setup_room(connect)
    await ready(ann)
    assert (await ann.request("room:leave"))["ok"]
    back = await connect()
    ack = await back.request("room:join", {"code": code, "profile": make_profile("Ann")})
    room = ack["data"]["room"]
    assert room["players"][1]["ready"] is False
    assert room["readyCheck"] == {"count": 0, "total": 1}


async def test_new_host_loses_their_flag(connect):
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"))
    await ready(ann)
    await ready(bob)
    assert (await host.request("room:leave"))["ok"]
    state = await bob.wait_push("room:state", lambda d: d["hostId"] == ann.player_id)
    assert ready_of(state, ann) is False and ready_of(state, bob) is True
    assert state["readyCheck"] == {"count": 1, "total": 1}


async def test_start_works_with_nobody_ready(connect):
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"))
    assert (await host.request("game:start"))["ok"]


# ----- resets ------------------------------------------------------------------------------------


async def test_changing_the_game_resets_and_tells_only_ready_players(connect):
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"))
    await ready(ann)
    await host.wait_push("room:state", ready_count(1))
    assert (await host.request("room:selectGame", {"gameId": "rps", "settings": {}}))["ok"]
    state = await bob.wait_push("room:state", lambda d: d["selectedGame"] == "rps")
    assert state["readyCheck"] == {"count": 0, "total": 2} and ready_of(state, ann) is False
    event = await ann.wait_push("room:event", lambda d: d["kind"] == "ready_reset")
    assert event == {
        "kind": "ready_reset",
        "playerId": host.player_id,
        "nickname": "Host",
        "data": {"reason": "game_changed"},
    }
    await bob.drain()
    await host.drain()
    assert not events(bob, "ready_reset") and not events(host, "ready_reset")


async def test_changing_a_setting_resets_with_settings_changed(connect):
    code, (host, ann) = await setup_room(connect, settings={"target": 2})
    await ready(ann)
    ack = await host.request("room:selectGame", {"gameId": "dummy", "settings": {"target": 3}})
    assert ack["ok"]
    event = await ann.wait_push("room:event", lambda d: d["kind"] == "ready_reset")
    assert event["data"] == {"reason": "settings_changed"}
    state = await latest_state(host)
    assert ready_of(state, ann) is False


async def test_unchanged_settings_do_not_reset(connect):
    code, (host, ann) = await setup_room(connect, settings={"target": 2})
    await ready(ann)
    # Same values, partly through the module's defaults: nothing actually changes.
    ack = await host.request("room:selectGame", {"gameId": "dummy", "settings": {}})
    assert ack["ok"]
    state = await latest_state(ann)
    assert ready_of(state, ann) is True
    assert not events(ann, "ready_reset")


async def test_starting_a_game_resets_everyone_without_an_event(connect, manager):
    code, (host, ann) = await setup_room(connect)
    await ready(ann)
    await start([host, ann])
    state = await latest_state(ann)
    assert ready_of(state, ann) is False and not events(ann, "ready_reset")


@pytest.mark.parametrize("how", ["play_again", "game_end"])
async def test_returning_to_the_lobby_resets(connect, manager, how):
    code, (host, ann) = await setup_room(connect, settings={"target": 1})
    await start([host, ann])
    room = manager.rooms[code]
    if how == "play_again":
        await host.request("game:action", {"type": "score"})
        await ann.wait_push("room:state", lambda d: d["status"] == "finished")
        room.player(ann.player_id).ready = True
        assert (await host.request("game:playAgain"))["ok"]
    else:
        room.player(ann.player_id).ready = True
        assert (await host.request("game:end"))["ok"]
    state = await ann.wait_push("room:state", lambda d: d["status"] == "lobby")
    assert ready_of(state, ann) is False


# ----- room:react --------------------------------------------------------------------------------


async def react(client, emoji="🔥"):
    return await client.request("room:react", {"emoji": emoji})


async def test_reaction_reaches_everyone_including_the_sender(connect):
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"))
    assert (await react(ann, "🎉"))["ok"]
    seen = [await c.wait_push("room:reaction") for c in (host, ann, bob)]
    assert seen[0] == seen[1] == seen[2]
    assert seen[0]["id"].startswith("r_")
    assert {k: seen[0][k] for k in ("playerId", "nickname", "emoji")} == {
        "playerId": ann.player_id,
        "nickname": "Ann",
        "emoji": "🎉",
    }


async def test_every_listed_emoji_is_accepted_and_others_are_not(connect, manager):
    manager.reaction_cooldown_ms = 0
    code, (host, ann) = await setup_room(connect)
    for emoji in REACTION_EMOJIS:
        assert (await react(ann, emoji))["ok"], emoji
    for bad in ["💩", "", "🔥🔥", 3, None, "❤"]:  # "❤" lacks the variation selector
        assert (await react(ann, bad))["error"]["code"] == "INVALID_ACTION", bad


async def test_reaction_cooldown(connect, manager):
    now = [1_000_000.0]
    manager.clock = lambda: now[0]
    code, (host, ann) = await setup_room(connect)
    assert (await react(ann))["ok"]
    now[0] += manager.reaction_cooldown_ms - 1
    assert (await react(ann))["error"]["code"] == "RATE_LIMITED"
    assert (await react(host))["ok"]  # the cooldown is per player
    now[0] += 1
    assert (await react(ann))["ok"]
    await host.drain()
    assert len([p for p in host.pushes if p["type"] == "room:reaction"]) == 3


async def test_reaction_needs_a_room(connect):
    stranger = await connect()
    assert (await react(stranger))["error"]["code"] == "NOT_IN_ROOM"


async def test_reactions_are_not_replayed_or_recorded(connect, monkeypatch):
    code, (host, ann) = await setup_room(connect)
    recorded = []
    monkeypatch.setattr(recorder, "record_event", lambda *a, **k: recorded.append(a))
    monkeypatch.setattr(recorder, "record_session", lambda *a, **k: recorded.append(a))
    assert (await react(host))["ok"]
    await ann.wait_push("room:reaction")
    token = ann.token
    await ann.close()
    again = await rejoin(connect, code, "Ann", token)
    await again.drain()
    assert not [p for p in again.pushes if p["type"] == "room:reaction"]
    assert recorded == []


async def test_forfeited_player_can_react_but_a_departed_one_cannot(connect):
    code, (host, ann, bob) = await setup_room(connect, ("Host", "Ann", "Bob"), {"target": 5})
    await start([host, ann, bob])
    assert (await ann.request("game:quit"))["ok"]
    assert (await react(ann, "😭"))["ok"]
    reaction = await host.wait_push("room:reaction")
    assert reaction["playerId"] == ann.player_id
    assert (await bob.request("room:leave"))["ok"]
    assert (await react(bob))["error"]["code"] == "NOT_IN_ROOM"
