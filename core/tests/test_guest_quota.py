"""Guests' free games: counted at game start, locked guests sit out or are turned away,
registered accounts untouched, and a broken quota table never blocks play."""

import time

import pytest
from channels.db import database_sync_to_async

from analytics import quota as quota_module
from analytics.keys import guest_key
from analytics.models import GuestQuota
from analytics.quota import prune_quota
from games.constants import GUEST_FREE_GAMES, GUEST_WINDOW_MS
from tests.conftest import make_profile
from tests.dummy_game import DummyGame
from tests.test_accounts_ws import make_account

pytestmark = pytest.mark.django_db(transaction=True)


def key(nickname: str) -> str:
    return guest_key(f"prof-{nickname}")


@database_sync_to_async
def plays() -> dict[str, int]:
    return dict(GuestQuota.objects.values_list("guest_key", "plays"))


@database_sync_to_async
def set_row(nickname: str, plays: int, window_start: float) -> None:
    GuestQuota.objects.update_or_create(
        guest_key=key(nickname), defaults={"plays": plays, "window_start": int(window_start)}
    )


def lock(nickname: str):
    return set_row(nickname, GUEST_FREE_GAMES, time.time() * 1000 - 1000)


async def room_with(connect, *nicknames, token=None):
    host = await connect()
    payload = {"profile": make_profile(nicknames[0])}
    if token:
        payload["authToken"] = token
    created = await host.request("room:create", payload)
    assert created["ok"], created
    code = created["data"]["room"]["code"]
    others = []
    for nickname in nicknames[1:]:
        client = await connect()
        ack = await client.request("room:join", {"code": code, "profile": make_profile(nickname)})
        assert ack["ok"], ack
        others.append((client, ack))
    assert (await host.request("room:selectGame", {"gameId": "dummy", "settings": {}}))["ok"]
    return host, created, others


async def test_each_guest_is_counted_once_at_start_and_told_what_is_left(connect) -> None:
    _, token = await make_account()
    host, created, [(ann, _)] = await room_with(connect, "Host", "Ann")
    acc = await connect()
    code = created["data"]["room"]["code"]
    assert (await acc.request("room:join", {"code": code, "authToken": token}))["ok"]
    assert (await host.request("game:start"))["ok"]
    assert await plays() == {key("Host"): 1, key("Ann"): 1}  # the account is never counted
    pushed = await ann.wait_push("guest:quota")
    assert pushed["remaining"] == GUEST_FREE_GAMES - 1 and pushed["lockedUntil"] is None
    assert pushed["limit"] == GUEST_FREE_GAMES and "serverNow" in pushed


async def test_window_resets_after_it_expires(connect) -> None:
    await set_row("Host", GUEST_FREE_GAMES, time.time() * 1000 - GUEST_WINDOW_MS - 1)
    host, _, _ = await room_with(connect, "Host")
    assert (await host.request("game:start"))["ok"]
    assert await plays() == {key("Host"): 1}


async def test_locked_guest_sits_out_and_is_not_counted(connect) -> None:
    host, created, [(ann, ann_ack), _] = await room_with(connect, "Host", "Ann", "Bob")
    await lock("Ann")
    assert (await host.request("game:start"))["ok"]
    state = await host.wait_push("room:state", lambda d: d["status"] == "playing")
    ann_seat = next(p for p in state["players"] if p["id"] == ann_ack["data"]["playerId"])
    assert ann_seat["inGame"] is False and ann_seat["locked"] is True
    assert all(p["locked"] is False for p in state["players"] if p["nickname"] != "Ann")
    assert (await plays())[key("Ann")] == GUEST_FREE_GAMES
    assert (await ann.wait_push("guest:quota"))["lockedUntil"] is not None


async def test_start_rejected_when_too_few_can_play(connect, monkeypatch) -> None:
    monkeypatch.setattr(DummyGame, "min_players", 2)
    host, created, _ = await room_with(connect, "Host", "Ann")
    await lock("Ann")
    ack = await host.request("game:start")
    assert not ack["ok"] and ack["error"]["code"] == "GUEST_LIMIT"
    assert ack["error"]["data"] == {"nicknames": ["Ann"]}
    assert key("Host") not in await plays()  # nobody is counted


async def test_locked_guest_cannot_take_a_new_seat_but_can_reconnect(connect) -> None:
    host, created, [(ann, ann_ack)] = await room_with(connect, "Host", "Ann")
    code = created["data"]["room"]["code"]
    await lock("Ann")
    for request, payload in [
        ("room:create", {"profile": make_profile("Ann")}),
        ("room:join", {"code": code, "profile": make_profile("Ann")}),
    ]:
        client = await connect()
        ack = await client.request(request, payload)
        assert not ack["ok"] and ack["error"]["code"] == "GUEST_LIMIT"
        assert ack["error"]["data"]["lockedUntil"] > time.time() * 1000
    again = await connect()
    token = ann_ack["data"]["roomToken"]
    ack = await again.request(
        "room:join", {"code": code, "profile": make_profile("Ann"), "roomToken": token}
    )
    assert ack["ok"], ack


async def test_registered_players_are_never_locked(connect) -> None:
    _, token = await make_account()
    client = await connect()
    created = await client.request("room:create", {"authToken": token})
    assert (await client.request("room:selectGame", {"gameId": "dummy", "settings": {}}))["ok"]
    for _ in range(GUEST_FREE_GAMES + 1):
        assert (await client.request("game:start"))["ok"]
        assert (await client.request("game:end"))["ok"]
    assert await plays() == {}
    assert created["ok"]


async def test_quota_request(connect) -> None:
    client = await connect()
    fresh = await client.request("guest:quota", {"profile": {"id": "prof-New"}})
    assert fresh["data"]["remaining"] == GUEST_FREE_GAMES and fresh["data"]["lockedUntil"] is None
    await lock("Ann")
    locked = await client.request("guest:quota", {"profile": {"id": "prof-Ann"}})
    assert locked["data"]["remaining"] == 0 and locked["data"]["lockedUntil"] is not None
    assert locked["data"]["limit"] == GUEST_FREE_GAMES and "serverNow" in locked["data"]


async def test_fails_open_when_the_table_is_broken(connect, monkeypatch, caplog) -> None:
    def broken(*_args):
        raise RuntimeError("db down")

    monkeypatch.setattr(quota_module, "read_quota", broken)
    monkeypatch.setattr(quota_module, "count_games", broken)
    host, _, _ = await room_with(connect, "Host", "Ann")
    assert (await host.request("game:start"))["ok"]
    assert "Guest quota" in caplog.text


async def test_prune_removes_expired_windows() -> None:
    now = time.time() * 1000
    await set_row("Old", 3, now - GUEST_WINDOW_MS - 1)
    await set_row("New", 3, now - 1000)
    assert await database_sync_to_async(prune_quota)(now) == 1
    assert list(await plays()) == [key("New")]
