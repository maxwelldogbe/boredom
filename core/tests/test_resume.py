"""Staying seated (PROTOCOL.md 4.11, 6.3): room:resume, takeover, one seat at a time, host delay."""

import pytest

from games.constants import HOST_OFFLINE_TRANSFER_MS
from tests.conftest import make_profile
from tests.test_accounts_ws import make_account

pytestmark = pytest.mark.django_db(transaction=True)


async def create(client, **payload):
    ack = await client.request("room:create", payload)
    assert ack["ok"], ack
    return ack["data"]["room"]["code"]


async def test_resume_finds_only_your_own_seat(connect, manager) -> None:
    _, token = await make_account("res_sam", "Sam")
    host = await connect()
    code = await create(host, authToken=token)
    other = await connect()
    seated = await other.request("room:resume", {"authToken": token})
    assert seated["data"]["resume"] == {
        "code": code,
        "roomToken": host.token,
        "status": "lobby",
        "hostNickname": "Sam",
        "playerCount": 1,
    }
    _, stranger = await make_account("res_ann", "Ann")
    assert (await other.request("room:resume", {"authToken": stranger}))["data"] == {"resume": None}


async def test_resume_for_a_guest_checks_the_stored_tokens(connect, manager) -> None:
    guest = await connect()
    code = await create(guest, profile=make_profile("Gus"))
    other = await connect()
    tokens = [{"code": "ZZZZ", "roomToken": "x"}, {"code": code, "roomToken": "wrong"}]
    ack = await other.request("room:resume", {"tokens": tokens})
    assert ack["data"] == {"resume": None}
    tokens.append({"code": code, "roomToken": guest.token})
    assert (await other.request("room:resume", {"tokens": tokens}))["data"]["resume"][
        "code"
    ] == code
    await guest.request("room:leave")
    assert (await other.request("room:resume", {"tokens": tokens}))["data"] == {"resume": None}


async def test_solo_rooms_are_never_resumed(connect, manager) -> None:
    _, token = await make_account("res_solo", "Sol")
    client = await connect()
    ack = await client.request("solo:start", {"authToken": token, "gameId": "tic_tac_toe"})
    assert ack["ok"]
    assert (await client.request("room:resume", {"authToken": token}))["data"] == {"resume": None}


async def test_takeover_tells_the_older_connection(connect, manager) -> None:
    old = await connect()
    code = await create(old, profile=make_profile("Gus"))
    new = await connect()
    payload = {"code": code, "profile": make_profile("Gus"), "roomToken": old.token}
    assert (await new.request("room:join", payload))["ok"]
    notice = await old.wait_push("error")
    assert notice == {
        "code": "NOT_IN_ROOM",
        "message": "You signed in elsewhere.",
        "data": {"reason": "signed_in_elsewhere"},
    }


async def test_one_seat_at_a_time(connect, manager, dummy_game) -> None:
    _, token = await make_account("res_one", "One")
    first = await connect()
    lobby = await create(first, authToken=token)
    second = await connect()
    playing = await create(second, authToken=token)
    assert lobby not in manager.rooms  # the old lobby seat was released (and its room emptied)
    friend = await connect()
    joined = await friend.request("room:join", {"code": playing, "profile": make_profile("Ann")})
    assert joined["ok"]
    assert (await second.request("room:selectGame", {"gameId": dummy_game.id, "settings": {}}))[
        "ok"
    ]
    assert (await second.request("game:start"))["ok"]
    third = await connect()
    ack = await third.request("room:create", {"authToken": token})
    assert ack["error"]["code"] == "ALREADY_IN_GAME"
    assert ack["error"]["data"] == {"code": playing}


async def test_host_waits_the_new_delay(manager) -> None:
    assert manager.host_transfer_ms == HOST_OFFLINE_TRANSFER_MS == 45000
