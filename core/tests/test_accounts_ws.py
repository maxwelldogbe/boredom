"""Accounts over the WebSocket: authToken seats, saved avatars, one seat per account,
stats after a finished game, and nothing account-related leaking into room:state.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

import pytest
from channels.db import database_sync_to_async
from django.contrib.auth.models import User

from accounts import rooms as account_rooms
from accounts.models import PlayerStats, Profile
from accounts.tokens import issue_token
from games.constants import AUTH_TOKEN_DAYS, PLAYER_COLORS
from rooms import hooks
from tests.conftest import make_profile

pytestmark = pytest.mark.django_db(transaction=True)

SAVED_AVATAR = {"style": "voxel-art", "seed": "saved123"}
PASSWORD = "correct horse battery"


@database_sync_to_async
def make_account(username: str = "sam_1", nickname: str = "Saved") -> tuple[User, str]:
    user = User.objects.create_user(username=username, password=PASSWORD)
    Profile.objects.create(
        user=user,
        nickname=nickname,
        color=PLAYER_COLORS[4],
        avatar_style=SAVED_AVATAR["style"],
        avatar_seed=SAVED_AVATAR["seed"],
    )
    return user, issue_token(user.pk)


@database_sync_to_async
def stats_rows() -> set[tuple[str, str, int, int]]:
    return set(PlayerStats.objects.values_list("user__username", "game_id", "played", "wins"))


async def create(connect, token=None, nickname="Host", **extra):
    client = await connect()
    payload = {"profile": make_profile(nickname), **extra}
    if token is not None:
        payload["authToken"] = token
    ack = await client.request("room:create", payload)
    assert ack["ok"], ack
    return client, ack


async def join(connect, code, token=None, nickname="Ann", **extra):
    client = await connect()
    payload = {"code": code, "profile": make_profile(nickname), **extra}
    if token is not None:
        payload["authToken"] = token
    return client, await client.request("room:join", payload)


def seat(room, player_id):
    return next(p for p in room["players"] if p["id"] == player_id)


async def test_valid_token_uses_saved_profile_and_ignores_client_fields(connect) -> None:
    _, token = await make_account()
    client, ack = await create(
        connect,
        token,
        "Spoof",
        profile=make_profile(
            "Spoof", color=PLAYER_COLORS[0], avatar={"style": "cutouts", "seed": "x"}
        ),
    )
    data = ack["data"]
    assert "authStatus" not in data
    me = seat(data["room"], data["playerId"])
    assert me["type"] == "registered"
    assert me["nickname"] == "Saved"
    assert me["color"] == PLAYER_COLORS[4]
    assert me["avatar"] == SAVED_AVATAR


async def test_valid_token_needs_no_client_profile(connect) -> None:
    _, token = await make_account()
    client = await connect()
    ack = await client.request("room:create", {"authToken": token})
    assert ack["ok"], ack
    assert seat(ack["data"]["room"], ack["data"]["playerId"])["nickname"] == "Saved"


async def test_saved_avatar_kept_across_rooms_and_games(connect) -> None:
    _, token = await make_account()
    _, first = await create(connect, token)
    _, second = await create(connect, token)
    _, guest_room = await create(connect, None, "Bob")
    _, third = await join(connect, guest_room["data"]["room"]["code"], token)
    for ack in (first, second, third):
        assert seat(ack["data"]["room"], ack["data"]["playerId"])["avatar"] == SAVED_AVATAR


async def test_guest_avatar_still_random_per_room(connect) -> None:
    avatars = []
    for _ in range(3):
        _, ack = await create(
            connect, None, "Sam", profile=make_profile("Sam", avatar=SAVED_AVATAR)
        )
        me = seat(ack["data"]["room"], ack["data"]["playerId"])
        assert me["type"] == "guest"
        avatars.append(json.dumps(me["avatar"], sort_keys=True))
    assert len(set(avatars)) == 3
    assert json.dumps(SAVED_AVATAR, sort_keys=True) not in avatars


async def test_no_token_is_unchanged_guest(connect) -> None:
    _, ack = await create(connect)
    assert "authStatus" not in ack["data"]
    assert seat(ack["data"]["room"], ack["data"]["playerId"])["type"] == "guest"


async def test_invalid_tokens_fall_back_to_guest_with_auth_status(connect) -> None:
    user, _ = await make_account()
    expired = issue_token(user.pk, datetime.now(UTC) - timedelta(days=AUTH_TOKEN_DAYS + 1))
    for bad in ["nonsense", expired, 42, ""]:
        _, ack = await create(connect, bad, "Guesty")
        data = ack["data"]
        assert data["authStatus"] == "invalid"
        me = seat(data["room"], data["playerId"])
        assert me["type"] == "guest" and me["nickname"] == "Guesty"
        assert me["avatar"] != SAVED_AVATAR


async def test_token_of_deleted_or_disabled_account_is_invalid(connect) -> None:
    user, token = await make_account()
    await database_sync_to_async(User.objects.filter(pk=user.pk).update)(is_active=False)
    _, ack = await create(connect, token)
    assert ack["data"]["authStatus"] == "invalid"
    await database_sync_to_async(User.objects.all().delete)()
    _, ack = await create(connect, token)
    assert ack["data"]["authStatus"] == "invalid"


async def test_invalid_token_with_invalid_profile_is_rejected(connect) -> None:
    client = await connect()
    ack = await client.request("room:create", {"authToken": "nonsense", "profile": {"id": "x"}})
    assert not ack["ok"] and ack["error"]["code"] == "INVALID_ACTION"


async def test_join_with_token_in_a_guest_room(connect) -> None:
    _, token = await make_account()
    host, created = await create(connect)
    _, ack = await join(connect, created["data"]["room"]["code"], token)
    me = seat(ack["data"]["room"], ack["data"]["playerId"])
    assert me["type"] == "registered" and me["nickname"] == "Saved"


async def test_same_account_never_holds_two_seats(connect) -> None:
    _, token = await make_account()
    host, created = await create(connect)
    code = created["data"]["room"]["code"]
    first, ack1 = await join(connect, code, token)
    second, ack2 = await join(connect, code, token)
    assert ack1["ok"] and ack2["ok"]
    assert ack2["data"]["playerId"] == ack1["data"]["playerId"]
    assert ack2["data"]["roomToken"] == ack1["data"]["roomToken"]
    assert len(ack2["data"]["room"]["players"]) == 2
    detached = await first.wait_push("error")
    assert detached["code"] == "NOT_IN_ROOM"


async def test_account_reclaims_its_seat_mid_game(connect, manager) -> None:
    _, token = await make_account()
    host, created = await create(connect, token)
    code = created["data"]["room"]["code"]
    _, ann = await join(connect, code, None, "Ann")
    assert (await host.request("room:selectGame", {"gameId": "dummy", "settings": {}}))["ok"]
    assert (await host.request("game:start"))["ok"]
    _, again = await join(connect, code, token)
    assert again["ok"], again
    assert again["data"]["playerId"] == created["data"]["playerId"]


async def test_room_state_exposes_only_type(connect) -> None:
    user, token = await make_account("secret_name")
    host, created = await create(connect, token)
    guest, ack = await join(connect, created["data"]["room"]["code"], None, "Ann")
    state = await host.wait_push("room:state", lambda d: len(d["players"]) == 2)
    text = json.dumps(state)
    for player in state["players"]:
        assert set(player) == {"id", "type", "nickname", "color", "avatar", "online", "joinedAt"}
    assert "profileId" not in text and "prof-Ann" not in text
    assert "secret_name" not in text and token not in text
    assert f"account-{user.pk}" not in text
    assert "userId" not in text and "username" not in text


async def play_dummy_game(connect, host_token=None, guest_token=None):
    """Host wins a one-point dummy game against Ann. Returns (host, ann, code)."""
    host, created = await create(connect, host_token)
    code = created["data"]["room"]["code"]
    ann, ack = await join(connect, code, guest_token, "Ann")
    assert ack["ok"]
    assert (await host.request("room:selectGame", {"gameId": "dummy", "settings": {"target": 1}}))[
        "ok"
    ]
    assert (await host.request("game:start"))["ok"]
    assert (await host.request("game:action", {"type": "score"}))["ok"]
    await ann.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    await hooks.drain()
    return host, ann, code


async def test_stats_updated_after_a_full_game(connect) -> None:
    _, host_token = await make_account("winner", "Win")
    _, ann_token = await make_account("loser", "Lose")
    host, ann, _ = await play_dummy_game(connect, host_token, ann_token)
    assert await stats_rows() == {("winner", "dummy", 1, 1), ("loser", "dummy", 1, 0)}

    assert (await host.request("game:playAgain"))["ok"]
    assert (await host.request("game:start"))["ok"]
    assert (await host.request("game:action", {"type": "score"}))["ok"]
    await ann.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    await hooks.drain()
    assert await stats_rows() == {("winner", "dummy", 2, 2), ("loser", "dummy", 2, 0)}


async def test_guests_get_no_stats(connect) -> None:
    _, token = await make_account("winner")
    await play_dummy_game(connect, token, None)
    assert await stats_rows() == {("winner", "dummy", 1, 1)}


async def test_stats_failure_does_not_break_the_game(connect, monkeypatch, caplog) -> None:
    async def broken(game_id, outcomes):
        raise RuntimeError("database is down")

    monkeypatch.setattr(account_rooms, "record_results", broken)
    _, token = await make_account()
    caplog.set_level(logging.ERROR, logger="rooms.hooks")
    host, ann, code = await play_dummy_game(connect, token, None)
    state = await ann.wait_push("room:state", lambda d: d["status"] == "finished")
    assert state["scoreboard"][host.player_id] == 100
    assert state["wins"] == {host.player_id: 1}
    assert "Stats update failed" in caplog.text
    assert (await host.request("game:playAgain"))["ok"]


async def test_hook_exception_does_not_break_the_game(connect, monkeypatch) -> None:
    def explode(*args):
        raise RuntimeError("hook bug")

    monkeypatch.setattr(hooks, "on_game_finished", explode)
    host, ann, _ = await play_dummy_game(connect)
    state = await ann.wait_push("room:state", lambda d: d["status"] == "finished")
    assert state["wins"] == {host.player_id: 1}


async def test_deleted_account_mid_game_is_skipped(connect, monkeypatch) -> None:
    _, token = await make_account("gone")
    _, other = await make_account("stays")
    real = account_rooms.record_results

    async def delete_first(game_id, outcomes):
        await database_sync_to_async(User.objects.filter(username="gone").delete)()
        await real(game_id, outcomes)

    monkeypatch.setattr(account_rooms, "record_results", delete_first)
    await play_dummy_game(connect, token, other)
    assert await stats_rows() == {("stays", "dummy", 1, 0)}


async def test_tokens_never_logged(connect, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    _, token = await make_account()
    await play_dummy_game(connect, token, "not-a-real-token")
    assert token not in caplog.text
    assert "not-a-real-token" not in caplog.text
    assert PASSWORD not in caplog.text
