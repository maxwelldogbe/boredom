"""Integration: room requests over a real /ws/ connection (create, join, peek, errors)."""

import json

from channels.testing import WebsocketCommunicator

from games.constants import MAX_PLAYERS
from tests.conftest import make_profile


async def create(connect, nickname="Host"):
    client = await connect()
    ack = await client.request("room:create", {"profile": make_profile(nickname)})
    assert ack["ok"], ack
    return client, ack["data"]["room"]["code"]


async def join(connect, code, nickname, **extra):
    client = await connect()
    ack = await client.request(
        "room:join", {"code": code, "profile": make_profile(nickname), **extra}
    )
    return client, ack


async def test_create_room_ack_and_state(connect):
    client = await connect()
    ack = await client.request("room:create", {"profile": make_profile("Sam")})
    data = ack["data"]
    assert ack["type"] == "ack" and ack["ok"] and ack["id"] == 1
    room = data["room"]
    assert len(room["code"]) == 4 and room["status"] == "lobby"
    assert room["hostId"] == data["playerId"]
    assert room["players"][0]["nickname"] == "Sam"
    assert set(room["players"][0]) == {
        "id",
        "type",
        "nickname",
        "avatar",
        "color",
        "online",
        "offlineSince",
        "inGame",
        "joinedAt",
        "ready",
    }
    assert room["scoreboard"] == {} and room["wins"] == {} and room["selectedGame"] is None
    assert room["readyCheck"] is None and room["players"][0]["ready"] is False
    assert room["endReason"] is None and room["players"][0]["inGame"] is True
    assert room["players"][0]["offlineSince"] is None
    assert data["roomToken"] and data["roomToken"] not in json.dumps(room)
    state = await client.wait_push("room:state")
    assert state["code"] == room["code"]


async def test_join_broadcasts_and_lowercase_code(connect):
    host, code = await create(connect)
    guest, ack = await join(connect, code.lower(), "Ann")
    assert ack["ok"] and len(ack["data"]["room"]["players"]) == 2
    state = await host.wait_push("room:state", lambda d: len(d["players"]) == 2)
    assert [p["nickname"] for p in state["players"]] == ["Host", "Ann"]
    assert "roomToken" not in json.dumps(state) and guest.token not in json.dumps(state)


async def test_duplicate_names_are_suffixed(connect):
    _, code = await create(connect, "Sam")
    _, a = await join(connect, code, "Sam")
    _, b = await join(connect, code, "sam")
    names = [p["nickname"] for p in b["data"]["room"]["players"]]
    assert a["ok"] and b["ok"] and names == ["Sam", "Sam2", "sam3"]


async def test_room_full(connect):
    _, code = await create(connect)
    for i in range(MAX_PLAYERS - 1):
        _, ack = await join(connect, code, f"P{i}")
        assert ack["ok"]
    _, ack = await join(connect, code, "Late")
    assert ack["error"]["code"] == "ROOM_FULL"


async def test_room_not_found_and_bad_code(connect):
    _, ack = await join(connect, "ZZZZ", "Ann")
    assert ack["error"]["code"] == "ROOM_NOT_FOUND"
    _, ack = await join(connect, "12", "Ann")
    assert ack["error"]["code"] == "ROOM_NOT_FOUND"


async def test_invalid_profile_rejected(connect):
    client = await connect()
    ack = await client.request(
        "room:create", {"profile": make_profile("Sam", avatar={"style": "nope", "seed": "x"})}
    )
    assert ack["error"]["code"] == "INVALID_ACTION"


async def test_peek(connect):
    _, code = await create(connect, "Sam")
    await join(connect, code, "Ann")
    outsider = await connect()
    ack = await outsider.request("room:peek", {"code": code.lower()})
    assert ack["data"] == {
        "exists": True,
        "hostNickname": "Sam",
        "playerCount": 2,
        "status": "lobby",
    }
    for bad in ["ZZZZ", "nope", None]:
        ack = await outsider.request("room:peek", {"code": bad})
        assert ack["ok"] and ack["data"] == {
            "exists": False,
            "hostNickname": None,
            "playerCount": 0,
            "status": None,
        }


async def test_host_only_requests(connect):
    host, code = await create(connect)
    guest, _ = await join(connect, code, "Ann")
    for type_, payload in [
        ("room:selectGame", {"gameId": "dummy", "settings": {}}),
        ("game:start", {}),
        ("game:playAgain", {}),
    ]:
        ack = await guest.request(type_, payload)
        assert ack["error"]["code"] == "NOT_HOST", type_


async def test_select_game_validates(connect):
    host, _ = await create(connect)
    ack = await host.request("room:selectGame", {"gameId": "chess", "settings": {}})
    assert ack["error"]["code"] == "INVALID_ACTION"
    ack = await host.request("room:selectGame", {"gameId": "dummy", "settings": {"target": 99}})
    assert ack["error"]["code"] == "INVALID_ACTION"
    ack = await host.request("room:selectGame", {"gameId": "dummy", "settings": {"target": 3}})
    assert ack["ok"]
    state = await host.wait_push("room:state", lambda d: d["selectedGame"] == "dummy")
    assert state["settings"] == {"target": 3, "turnMs": 10_000}


async def test_start_requires_selected_game(connect):
    host, _ = await create(connect)
    ack = await host.request("game:start")
    assert ack["error"]["code"] == "INVALID_ACTION"


async def test_not_in_room_requests(connect):
    client = await connect()
    for type_ in ["room:leave", "room:selectGame", "game:start", "game:action", "game:playAgain"]:
        ack = await client.request(type_, {})
        assert ack["error"]["code"] == "NOT_IN_ROOM", type_


async def test_cannot_join_twice_on_one_socket(connect):
    host, code = await create(connect)
    ack = await host.request("room:join", {"code": code, "profile": make_profile("Again")})
    assert ack["error"]["code"] == "INVALID_ACTION"


async def test_unknown_event(connect):
    client = await connect()
    ack = await client.request("room:explode", {})
    assert ack["error"]["code"] == "UNKNOWN_EVENT"


async def test_bad_messages(connect):
    client = await connect()
    await client.comm.send_to(text_data="{not json")
    assert (await client.recv())["type"] == "error"
    await client.comm.send_to(bytes_data=b"\x00\x01")
    msg = await client.recv()
    assert msg == {
        "type": "error",
        "data": {"code": "BAD_MESSAGE", "message": msg["data"]["message"]},
    }
    await client.comm.send_to(text_data=json.dumps({"id": 9, "type": "room:peek"}))
    msg = await client.recv()
    assert msg["type"] == "ack" and msg["id"] == 9 and msg["error"]["code"] == "BAD_MESSAGE"
    ack = await client.request("room:peek", {"code": "ABCD"})  # socket still usable
    assert ack["ok"]


async def test_disallowed_origin_is_refused(manager):
    from config.asgi import application

    comm = WebsocketCommunicator(application, "/ws/", headers=[(b"origin", b"http://evil.example")])
    connected, _ = await comm.connect()
    assert not connected


async def test_leave_in_lobby_removes_player_and_transfers_host(connect, manager):
    host, code = await create(connect, "Host")
    guest, _ = await join(connect, code, "Ann")
    assert (await host.request("room:leave"))["ok"]
    state = await guest.wait_push("room:state", lambda d: len(d["players"]) == 1)
    assert state["hostId"] == guest.player_id
    assert (await guest.request("room:leave"))["ok"]
    assert code not in manager.rooms
