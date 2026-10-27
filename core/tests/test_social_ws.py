"""Presence, friend pushes, room invites and by-player actions over the WebSocket (Part 2)."""

import asyncio
import itertools
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.test import Client

from accounts import admin as accounts_admin
from accounts import services as account_services
from accounts.tokens import issue_token
from games.constants import PLAYER_COLORS
from rooms.manager import RoomManager
from rooms.models_types import Avatar
from social import services
from social.hub import SocialHub
from social.models import Block, Friendship, Report
from tests.conftest import make_profile

pytestmark = pytest.mark.django_db(transaction=True)

_names = itertools.count(1)


@pytest.fixture(autouse=True)
def fast(manager: RoomManager) -> SocialHub:
    hub = manager.social
    hub.offline_delay_ms = 150
    services.request_limiter.reset()
    return hub


@database_sync_to_async
def make_user(nickname: str) -> User:
    n = next(_names)
    return account_services.create_account(
        f"secret_login_{n}",
        "correct horse battery",
        nickname,
        PLAYER_COLORS[3],
        Avatar("cutouts", f"seed{n}"),
        {},
    )


@database_sync_to_async
def befriend(a: User, b: User) -> None:
    low, high = sorted((a.pk, b.pk))
    Friendship.objects.create(user_low_id=low, user_high_id=high)


@database_sync_to_async
def tag_of(user: User) -> str:
    user.profile.refresh_from_db()
    return user.profile.tag


async def online(connect, user: User):
    """A connection that sent auth:hello for `user` (snapshot consumed)."""
    client = await connect()
    ack = await client.request("auth:hello", {"authToken": issue_token(user.pk)})
    assert ack["ok"], ack
    await client.wait_push("friends:snapshot")
    return client


async def host_room(client, user: User | None = None, nickname="Host") -> str:
    payload: dict[str, Any] = {"profile": make_profile(nickname)}
    if user is not None:
        payload["authToken"] = issue_token(user.pk)
    ack = await client.request("room:create", payload)
    assert ack["ok"], ack
    return ack["data"]["room"]["code"]


async def join(client, code: str, user: User | None = None, nickname="Guest"):
    payload: dict[str, Any] = {"code": code, "profile": make_profile(nickname)}
    if user is not None:
        payload["authToken"] = issue_token(user.pk)
    ack = await client.request("room:join", payload)
    assert ack["ok"], ack
    return ack


async def presence(client, tag: str, status: str) -> None:
    await client.wait_push("friends:presence", lambda d: d == {"tag": tag, "status": status})


async def quiet(client, type_: str, seconds: float = 0.25) -> None:
    """No push of `type_` arrives within `seconds`."""
    await asyncio.sleep(seconds)
    await client.drain()
    assert client.latest(type_) is None, client.pushes


def code(ack) -> str:
    return ack["error"]["code"]


# ----- auth:hello -------------------------------------------------------------------------------


async def test_hello_binds_and_sends_the_snapshot(connect) -> None:
    ann, bob, cat = await make_user("Ann"), await make_user("Bob"), await make_user("Cat")
    await befriend(ann, bob)
    await befriend(ann, cat)
    await online(connect, bob)
    client = await connect()
    ack = await client.request("auth:hello", {"authToken": issue_token(ann.pk)})
    assert ack["ok"] and ack["data"] == {"presence": "online"}
    snapshot = await client.wait_push("friends:snapshot")
    assert sorted(snapshot["friends"], key=lambda f: f["tag"]) == sorted(
        [
            {"tag": await tag_of(bob), "status": "online"},
            {"tag": await tag_of(cat), "status": "offline"},
        ],
        key=lambda f: f["tag"],
    )


async def test_bad_tokens_leave_the_connection_a_guest(connect, manager) -> None:
    ann = await make_user("Ann")
    disabled = await make_user("Dis")
    disabled.is_active = False
    await database_sync_to_async(disabled.save)()
    expired = issue_token(ann.pk, now=datetime.now(UTC) - timedelta(days=60))
    client = await connect()
    for token in ("nonsense", None, expired, issue_token(disabled.pk), issue_token(99999)):
        ack = await client.request("auth:hello", {"authToken": token})
        assert not ack["ok"] and code(ack) == "UNAUTHORIZED"
    assert manager.social.accounts == {} and manager.social.owners == {}
    # a bound connection that sends a bad token is signed out
    await client.request("auth:hello", {"authToken": issue_token(ann.pk)})
    assert list(manager.social.owners.values()) == [ann.pk]
    await client.request("auth:hello", {"authToken": "nonsense"})
    assert manager.social.owners == {}


async def test_room_create_with_auth_token_still_works_without_hello(connect, manager) -> None:
    ann = await make_user("Ann")
    client = await connect()
    await host_room(client, ann)
    room = next(iter(manager.rooms.values()))
    assert room.players[0].user_id == ann.pk
    assert manager.social.accounts == {}  # only auth:hello binds presence


# ----- presence ---------------------------------------------------------------------------------


async def test_multiple_connections_and_no_flicker(connect, fast) -> None:
    ann, bob = await make_user("Ann"), await make_user("Bob")
    await befriend(ann, bob)
    watcher = await online(connect, bob)
    ann_tag = await tag_of(ann)
    first = await online(connect, ann)
    await presence(watcher, ann_tag, "online")
    second = await online(connect, ann)
    await first.close()
    await quiet(watcher, "friends:presence")  # still one connection
    await second.close()
    await asyncio.sleep(fast.offline_delay_ms / 1000 / 3)
    await online(connect, ann)  # back within the delay
    await quiet(watcher, "friends:presence", fast.offline_delay_ms / 1000 * 1.5)
    assert fast.status(ann.pk) == "online"


async def test_offline_after_the_delay(connect, fast) -> None:
    ann, bob = await make_user("Ann"), await make_user("Bob")
    await befriend(ann, bob)
    watcher = await online(connect, bob)
    client = await online(connect, ann)
    await presence(watcher, await tag_of(ann), "online")
    await client.close()
    await quiet(watcher, "friends:presence", fast.offline_delay_ms / 1000 / 2)
    await presence(watcher, await tag_of(ann), "offline")


async def test_every_status(connect, fast) -> None:
    ann, bob = await make_user("Ann"), await make_user("Bob")
    await befriend(ann, bob)
    watcher = await online(connect, bob)
    tag = await tag_of(ann)
    client = await online(connect, ann)
    await presence(watcher, tag, "online")
    code_ = await host_room(client, ann)
    await presence(watcher, tag, "in_lobby")
    guest = await connect()
    await join(guest, code_)
    await client.request("room:selectGame", {"gameId": "dummy", "settings": {}})
    assert (await client.request("game:start"))["ok"]
    await presence(watcher, tag, "in_game")
    await client.request("game:quit")  # forfeited: still seated, no longer in the game
    await presence(watcher, tag, "in_lobby")
    await client.request("room:leave")
    await presence(watcher, tag, "online")
    patch = sync_to_async(_patch_settings)
    await patch(ann, "busy")
    await presence(watcher, tag, "busy")
    await patch(ann, "offline")
    await presence(watcher, tag, "offline")
    await patch(ann, "online")
    await presence(watcher, tag, "online")


def _patch_settings(user: User, mode: str) -> None:
    response = Client().patch(
        "/api/me/settings",
        data=json.dumps({"presence": mode}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {issue_token(user.pk)}",
    )
    assert response.status_code == 200


async def test_hello_reports_the_saved_presence_mode(connect) -> None:
    ann, bob = await make_user("Ann"), await make_user("Bob")
    await befriend(ann, bob)
    await sync_to_async(_patch_settings)(ann, "busy")
    client = await connect()
    ack = await client.request("auth:hello", {"authToken": issue_token(ann.pk)})
    assert ack["data"] == {"presence": "busy"}
    watcher = await connect()
    await watcher.request("auth:hello", {"authToken": issue_token(bob.pk)})
    snapshot = await watcher.wait_push("friends:snapshot")
    assert snapshot["friends"] == [{"tag": await tag_of(ann), "status": "busy"}]


async def test_presence_goes_only_to_friends(connect) -> None:
    ann, bob, stranger = await make_user("Ann"), await make_user("Bob"), await make_user("Zed")
    await befriend(ann, bob)
    friend = await online(connect, bob)
    other = await online(connect, stranger)
    guest = await connect()
    client = await online(connect, ann)
    await presence(friend, await tag_of(ann), "online")
    await host_room(client, ann)
    await presence(friend, await tag_of(ann), "in_lobby")
    await quiet(other, "friends:presence")
    await guest.drain()
    assert guest.pushes == []


# ----- friend pushes ----------------------------------------------------------------------------


def _post(user: User, path: str, body: dict | None = None):
    return Client().post(
        path,
        data=json.dumps(body or {}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {issue_token(user.pk)}",
    )


def _delete(user: User, path: str):
    return Client().delete(path, HTTP_AUTHORIZATION=f"Bearer {issue_token(user.pk)}")


async def test_request_accept_remove_pushes(connect) -> None:
    ann, bob, cat = await make_user("Ann"), await make_user("Bob"), await make_user("Cat")
    a, b, c = await online(connect, ann), await online(connect, bob), await online(connect, cat)
    ann_tag, bob_tag = await tag_of(ann), await tag_of(bob)
    await sync_to_async(_post)(ann, "/api/friends/requests", {"tag": bob_tag})
    pushed = await b.wait_push("friends:request")
    assert pushed["request"]["tag"] == ann_tag and pushed["request"]["nickname"] == "Ann"
    assert set(pushed["request"]) == {
        "requestId",
        "tag",
        "nickname",
        "avatar",
        "color",
        "createdAt",
    }
    rid = pushed["request"]["requestId"]
    await sync_to_async(_post)(bob, f"/api/friends/requests/{rid}/accept")
    assert await a.wait_push("friends:accepted") == {"tag": bob_tag, "nickname": "Bob"}
    assert await b.wait_push("friends:accepted") == {"tag": ann_tag, "nickname": "Ann"}
    await presence(a, bob_tag, "online")
    await presence(b, ann_tag, "online")
    # live from now on
    await host_room(b, bob)
    await presence(a, bob_tag, "in_lobby")
    await sync_to_async(_delete)(ann, f"/api/friends/{bob_tag}")
    assert await b.wait_push("friends:removed") == {"tag": ann_tag}
    assert await a.wait_push("friends:removed") == {"tag": bob_tag}
    await b.request("room:leave")
    await quiet(a, "friends:presence")
    await quiet(c, "friends:request", 0.05)
    assert c.pushes == []


async def test_crossed_request_pushes_accepted(connect) -> None:
    ann, bob = await make_user("Ann"), await make_user("Bob")
    a = await online(connect, ann)
    await sync_to_async(_post)(ann, "/api/friends/requests", {"tag": await tag_of(bob)})
    await sync_to_async(_post)(bob, "/api/friends/requests", {"tag": await tag_of(ann)})
    assert (await a.wait_push("friends:accepted"))["nickname"] == "Bob"


async def test_block_removes_silently_and_only_former_friends_hear(connect) -> None:
    ann, bob, cat = await make_user("Ann"), await make_user("Bob"), await make_user("Cat")
    await befriend(ann, bob)
    a, b, c = await online(connect, ann), await online(connect, bob), await online(connect, cat)
    await sync_to_async(_post)(ann, "/api/blocks", {"tag": await tag_of(bob)})
    assert await b.wait_push("friends:removed") == {"tag": await tag_of(ann)}
    await sync_to_async(_post)(ann, "/api/blocks", {"tag": await tag_of(cat)})
    await quiet(c, "friends:removed")  # cat was never a friend: no tag is pushed
    await a.drain()


async def test_disabling_drops_the_account_live(connect, manager) -> None:
    ann, bob = await make_user("Ann"), await make_user("Bob")
    await befriend(ann, bob)
    watcher = await online(connect, bob)
    await online(connect, ann)
    await presence(watcher, await tag_of(ann), "online")

    def disable() -> None:
        accounts_admin.set_active(
            _FakeRequest(), _FakeAdmin(), User.objects.filter(pk=ann.pk), False
        )

    await sync_to_async(disable)()
    assert await watcher.wait_push("friends:removed") == {"tag": await tag_of(ann)}
    assert ann.pk not in manager.social.accounts


class _FakeAdmin:
    def log_change(self, *args: Any) -> None:
        pass


class _FakeRequest:
    pass


# ----- invites ----------------------------------------------------------------------------------


async def lobby_with_friend(connect):
    """Ann hosts a lobby; Bob (her friend) is online on the home screen."""
    ann, bob = await make_user("Ann"), await make_user("Bob")
    await befriend(ann, bob)
    a = await online(connect, ann)
    room_code = await host_room(a, ann)
    b = await online(connect, bob)
    return ann, bob, a, b, room_code


async def test_invite_round_trip(connect, manager) -> None:
    ann, bob, a, b, room_code = await lobby_with_friend(connect)
    ack = await a.request("invite:send", {"tag": "#" + (await tag_of(bob)).lower()})
    assert ack["ok"], ack
    received = await b.wait_push("invite:received")
    assert set(received) == {
        "inviteId",
        "fromTag",
        "fromNickname",
        "fromAvatar",
        "gameId",
        "expiresAt",
        "serverNow",
    }
    assert received["fromTag"] == await tag_of(ann) and received["fromNickname"] == "Ann"
    assert received["gameId"] is None
    assert received["expiresAt"] == pytest.approx(received["serverNow"] + 120_000, abs=50)
    assert room_code not in json.dumps(received)
    # only the recipient can accept
    stranger = await online(connect, await make_user("Zed"))
    assert code(await stranger.request("invite:accept", {"inviteId": received["inviteId"]})) == (
        "INVITE_INVALID"
    )
    assert code(await a.request("invite:accept", {"inviteId": received["inviteId"]})) == (
        "INVITE_INVALID"
    )
    accepted = await b.request("invite:accept", {"inviteId": received["inviteId"]})
    assert accepted["ok"] and accepted["data"] == {"code": room_code}
    again = await b.request("invite:accept", {"inviteId": received["inviteId"]})
    assert code(again) == "INVITE_INVALID"
    await join(b, room_code, bob)
    assert len(manager.rooms[room_code].players) == 2


async def test_invite_send_errors(connect, manager, fast) -> None:
    ann, bob = await make_user("Ann"), await make_user("Bob")
    await befriend(ann, bob)
    a = await online(connect, ann)
    bob_tag = await tag_of(bob)
    assert code(await a.request("invite:send", {"tag": bob_tag})) == "NOT_IN_ROOM"
    guest = await connect()
    await host_room(guest)
    assert code(await guest.request("invite:send", {"tag": bob_tag})) == "INVALID_ACTION"
    await host_room(a, ann)
    await online(connect, bob)
    stranger = await make_user("Zed")
    assert code(await a.request("invite:send", {"tag": await tag_of(stranger)})) == "NOT_FRIENDS"
    assert code(await a.request("invite:send", {"tag": "ZZZZZZ"})) == "NOT_FRIENDS"
    assert code(await a.request("invite:send", {"tag": 5})) == "NOT_FRIENDS"
    await a.request("room:selectGame", {"gameId": "dummy", "settings": {}})
    await a.request("game:start")
    assert code(await a.request("invite:send", {"tag": bob_tag})) == "INVALID_ACTION"


async def test_room_full_for_the_selected_game(connect) -> None:
    ann, bob, a, b, room_code = await lobby_with_friend(connect)
    await a.request("room:selectGame", {"gameId": "dots_and_boxes", "settings": {}})
    for i in range(3):
        await join(await connect(), room_code, nickname=f"G{i}")
    assert code(await a.request("invite:send", {"tag": await tag_of(bob)})) == "ROOM_FULL"


async def test_target_unavailable_is_generic(connect, manager) -> None:
    ann = await make_user("Ann")
    a = await online(connect, ann)
    await host_room(a, ann)
    messages = set()

    async def friend(nickname: str) -> User:
        user = await make_user(nickname)
        await befriend(ann, user)
        return user

    offline = await friend("Off")
    busy = await friend("Busy")
    await online(connect, busy)
    await sync_to_async(_patch_settings)(busy, "busy")
    hidden = await friend("Hid")
    await online(connect, hidden)
    await sync_to_async(_patch_settings)(hidden, "offline")
    seated = await friend("Seat")
    await host_room(await online(connect, seated), seated)
    blocker = await friend("Blk")
    await online(connect, blocker)
    await sync_to_async(_post)(blocker, "/api/blocks", {"tag": await tag_of(ann)})
    disabled = await friend("Dis")
    await online(connect, disabled)
    await sync_to_async(lambda: User.objects.filter(pk=disabled.pk).update(is_active=False))()
    await asyncio.sleep(0.05)
    for target in (offline, busy, hidden, seated, blocker, disabled):
        ack = await a.request("invite:send", {"tag": await tag_of(target)})
        assert code(ack) == "TARGET_UNAVAILABLE", (target.profile.nickname, ack)
        messages.add(ack["error"]["message"])
    assert len(messages) == 1


async def test_invite_rate_limits(connect, manager) -> None:
    ann, bob, a, b, room_code = await lobby_with_friend(connect)
    manager.social.invite_limiter.limit = 3
    bob_tag = await tag_of(bob)
    assert (await a.request("invite:send", {"tag": bob_tag}))["ok"]
    cooling = await a.request("invite:send", {"tag": bob_tag})  # same pair within the cooldown
    assert code(cooling) == "RATE_LIMITED"
    manager.social.invite_cooldown_ms = 0
    assert (await a.request("invite:send", {"tag": bob_tag}))["ok"]
    assert (await a.request("invite:send", {"tag": bob_tag}))["ok"]
    assert code(await a.request("invite:send", {"tag": bob_tag})) == "RATE_LIMITED"  # per minute
    # each newer invite from the same sender replaced the older one
    await asyncio.sleep(0.05)
    await b.drain()
    received = [p["data"]["inviteId"] for p in b.pushes if p["type"] == "invite:received"]
    expired = [p["data"]["inviteId"] for p in b.pushes if p["type"] == "invite:expired"]
    assert len(received) == 3 and expired == received[:2]
    assert [i.id for i in manager.social.invites.values()] == received[2:]


async def test_pending_invites_are_capped(connect, manager, monkeypatch) -> None:
    from social import hub as hub_module

    monkeypatch.setattr(hub_module, "MAX_PENDING_INVITES_PER_USER", 2)
    bob = await make_user("Bob")
    b = await online(connect, bob)
    ids = []
    for name in ("A1", "A2", "A3"):
        sender = await make_user(name)
        await befriend(sender, bob)
        client = await online(connect, sender)
        await host_room(client, sender)
        assert (await client.request("invite:send", {"tag": await tag_of(bob)}))["ok"]
        ids.append((await b.wait_push("invite:received"))["inviteId"])
    assert (await b.wait_push("invite:expired")) == {"inviteId": ids[0]}
    assert sorted(i.id for i in manager.social.invites.values()) == sorted(ids[1:])


async def test_multi_device_clearing_and_silent_decline(connect) -> None:
    ann, bob, a, b, room_code = await lobby_with_friend(connect)
    b2 = await online(connect, bob)
    await a.request("invite:send", {"tag": await tag_of(bob)})
    first = (await b.wait_push("invite:received"))["inviteId"]
    assert (await b2.wait_push("invite:received"))["inviteId"] == first
    await b.request("invite:accept", {"inviteId": first})
    assert await b2.wait_push("invite:cleared") == {"inviteId": first}
    await a.drain()
    a.pushes.clear()
    from rooms import manager as manager_module

    manager_module.manager.social.invite_cooldown_ms = 0
    await a.request("invite:send", {"tag": await tag_of(bob)})
    second = (await b2.wait_push("invite:received"))["inviteId"]
    assert (await b2.request("invite:decline", {"inviteId": second}))["ok"]
    assert await b.wait_push("invite:cleared", lambda d: d["inviteId"] == second)
    assert (await b.request("invite:decline", {"inviteId": "nope"}))["ok"]
    await a.drain()
    assert [p for p in a.pushes if p["type"].startswith("invite")] == []


async def test_new_device_gets_pending_invites(connect) -> None:
    ann, bob, a, b, room_code = await lobby_with_friend(connect)
    await a.request("invite:send", {"tag": await tag_of(bob)})
    invite_id = (await b.wait_push("invite:received"))["inviteId"]
    late = await connect()
    await late.request("auth:hello", {"authToken": issue_token(bob.pk)})
    assert (await late.wait_push("invite:received"))["inviteId"] == invite_id


async def _invited(connect):
    ann, bob, a, b, room_code = await lobby_with_friend(connect)
    await a.request("invite:send", {"tag": await tag_of(bob)})
    invite_id = (await b.wait_push("invite:received"))["inviteId"]
    return ann, bob, a, b, room_code, invite_id


async def test_expires_when_the_game_starts(connect) -> None:
    ann, bob, a, b, room_code, invite_id = await _invited(connect)
    await a.request("room:selectGame", {"gameId": "dummy", "settings": {}})
    await a.request("game:start")
    assert await b.wait_push("invite:expired") == {"inviteId": invite_id}
    assert code(await b.request("invite:accept", {"inviteId": invite_id})) == "INVITE_EXPIRED"
    stranger = await online(connect, await make_user("Zed"))
    assert code(await stranger.request("invite:accept", {"inviteId": invite_id})) == (
        "INVITE_INVALID"
    )


async def test_expires_when_the_room_closes(connect) -> None:
    ann, bob, a, b, room_code, invite_id = await _invited(connect)
    await a.request("room:leave")  # the only player: the room is deleted
    assert await b.wait_push("invite:expired") == {"inviteId": invite_id}


async def test_expires_when_the_sender_leaves(connect) -> None:
    ann, bob, a, b, room_code, invite_id = await _invited(connect)
    await join(await connect(), room_code, nickname="Stay")
    await a.request("room:leave")
    assert await b.wait_push("invite:expired") == {"inviteId": invite_id}


async def test_expires_when_the_room_fills(connect) -> None:
    ann, bob, a, b, room_code, invite_id = await _invited(connect)
    await a.request("room:selectGame", {"gameId": "dots_and_boxes", "settings": {}})
    for i in range(3):
        await join(await connect(), room_code, nickname=f"G{i}")
    assert await b.wait_push("invite:expired") == {"inviteId": invite_id}


async def test_expires_after_the_ttl(connect, manager) -> None:
    manager.social.invite_ttl_ms = 150
    ann, bob, a, b, room_code, invite_id = await _invited(connect)
    assert await b.wait_push("invite:expired") == {"inviteId": invite_id}
    assert code(await b.request("invite:accept", {"inviteId": invite_id})) == "INVITE_EXPIRED"


async def test_accept_after_expiry_time_is_expired(connect, manager) -> None:
    ann, bob, a, b, room_code, invite_id = await _invited(connect)
    manager.social.invites[invite_id].expires_at = manager.clock() - 1
    assert code(await b.request("invite:accept", {"inviteId": invite_id})) == "INVITE_EXPIRED"


async def test_accept_refused_after_a_block(connect, manager) -> None:
    ann, bob, a, b, room_code, invite_id = await _invited(connect)
    await database_sync_to_async(Block.objects.create)(blocker=bob, blocked=ann)
    assert code(await b.request("invite:accept", {"inviteId": invite_id})) == "INVITE_INVALID"


async def test_a_restart_drops_invites(connect, manager, monkeypatch) -> None:
    ann, bob, a, b, room_code, invite_id = await _invited(connect)
    from rooms import manager as manager_module

    restarted = RoomManager()
    monkeypatch.setattr(manager_module, "manager", restarted)
    fresh = await connect()
    await fresh.request("auth:hello", {"authToken": issue_token(bob.pk)})
    await fresh.drain()
    assert [p for p in fresh.pushes if p["type"] == "invite:received"] == []
    assert code(await fresh.request("invite:accept", {"inviteId": invite_id})) == "INVITE_INVALID"
    for task in restarted.social.tasks():
        task.cancel()


# ----- by-player actions ------------------------------------------------------------------------


async def _shared_room(connect):
    ann, bob = await make_user("Ann"), await make_user("Bob")
    a, b = await connect(), await connect()
    room_code = await host_room(a, ann)
    bob_seat = (await join(b, room_code, bob))["data"]["playerId"]
    guest = await connect()
    guest_seat = (await join(guest, room_code, nickname="Gus"))["data"]["playerId"]
    return ann, bob, a, b, guest, room_code, bob_seat, guest_seat


async def test_request_and_block_by_player(connect) -> None:
    ann, bob, a, b, guest, room_code, bob_seat, guest_seat = await _shared_room(connect)
    ack = await a.request("friends:requestByPlayer", {"playerId": bob_seat})
    assert ack["ok"] and ack["data"] == {"status": "requested"}
    assert code(await a.request("friends:requestByPlayer", {"playerId": bob_seat})) == (
        "ALREADY_REQUESTED"
    )
    assert code(await a.request("friends:requestByPlayer", {"playerId": guest_seat})) == (
        "INVALID_ACTION"
    )
    assert code(await a.request("player:block", {"playerId": guest_seat})) == "INVALID_ACTION"
    assert code(await guest.request("player:block", {"playerId": bob_seat})) == "INVALID_ACTION"
    assert code(await a.request("player:block", {"playerId": "p_nobody"})) == "INVALID_ACTION"
    assert (await a.request("player:block", {"playerId": bob_seat}))["ok"]
    assert await database_sync_to_async(Block.objects.filter(blocker=ann, blocked=bob).exists)()
    # a block never affects room membership
    await a.drain()
    assert len(a.latest("room:state")["players"]) == 3


async def test_by_player_needs_the_same_room(connect) -> None:
    ann, bob = await make_user("Ann"), await make_user("Bob")
    a, b = await connect(), await connect()
    await host_room(a, ann)
    other = await host_room(b, bob)
    assert other
    bob_seat = b.player_id
    assert code(await a.request("friends:requestByPlayer", {"playerId": bob_seat})) == (
        "INVALID_ACTION"
    )
    lonely = await connect()
    assert code(await lonely.request("player:report", {"playerId": bob_seat})) == "NOT_IN_ROOM"


async def test_report_by_player_on_guest_and_registered(connect, manager) -> None:
    ann, bob, a, b, guest, room_code, bob_seat, guest_seat = await _shared_room(connect)
    await a.request("room:selectGame", {"gameId": "dummy", "settings": {}})
    ack = await a.request(
        "player:report", {"playerId": guest_seat, "reason": "spam", "note": "hi\x07"}
    )
    assert ack["ok"] and ack["data"] == {}
    assert (await a.request("player:report", {"playerId": bob_seat, "reason": "cheating"}))["ok"]
    assert code(await a.request("player:report", {"playerId": bob_seat, "reason": "x"})) == (
        "INVALID_INPUT"
    )
    assert code(await guest.request("player:report", {"playerId": bob_seat, "reason": "spam"})) == (
        "INVALID_ACTION"
    )
    rows = await database_sync_to_async(lambda: list(Report.objects.order_by("pk")))()
    seat = manager.rooms[room_code].player(guest_seat)
    assert rows[0].reported_user_id is None and rows[0].reported_guest_key == seat.guest_key
    assert rows[0].reported_nickname == "Gus" and rows[0].note == "hi"
    assert rows[0].room_code == room_code and rows[0].game_id == "dummy"
    assert rows[1].reported_user_id == bob.pk and rows[1].reported_nickname == "Bob"


# ----- privacy ----------------------------------------------------------------------------------


async def test_no_ids_usernames_or_room_codes_in_social_pushes(connect, manager) -> None:
    ann, bob = await make_user("Ann"), await make_user("Bob")
    await befriend(ann, bob)
    a = await online(connect, ann)
    b = await online(connect, bob)
    room_code = await host_room(a, ann)
    await a.request("invite:send", {"tag": await tag_of(bob)})
    b.pushes.append({"type": "invite:received", "data": await b.wait_push("invite:received")})
    await sync_to_async(_post)(ann, "/api/blocks", {"tag": await tag_of(bob)})
    await asyncio.sleep(0.1)
    await b.drain()
    social = [p for p in b.pushes if p["type"].split(":")[0] in ("friends", "invite")]
    assert {p["type"] for p in social} >= {"friends:presence", "invite:received", "friends:removed"}
    text = json.dumps(social)
    for secret in (ann.username, bob.username, room_code, f'"{ann.pk}"'):
        assert secret not in text
    assert "userId" not in text and "username" not in text


async def test_http_friend_list_shows_live_status(connect) -> None:
    ann, bob = await make_user("Ann"), await make_user("Bob")
    await befriend(ann, bob)
    client = await online(connect, ann)
    await host_room(client, ann)

    def friends() -> list:
        response = Client().get("/api/friends", HTTP_AUTHORIZATION=f"Bearer {issue_token(bob.pk)}")
        return response.json()["friends"]

    assert [f["status"] for f in await sync_to_async(friends)()] == ["in_lobby"]
