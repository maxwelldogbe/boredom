"""Friends, blocks, reports and the presence setting over HTTP (Part 1 of the social feature)."""

import itertools
import json
from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from accounts import services as account_services
from accounts.models import PlayerStats
from accounts.tokens import issue_token
from games.constants import PLAYER_COLORS, REPORT_NOTE_MAX, REPORT_REASONS, REPORTS_PER_DAY
from rooms.models_types import Avatar
from social import services
from social.models import Block, FriendRequest, Friendship, Report
from tests.test_profile_api import session

pytestmark = pytest.mark.django_db

_names = itertools.count(1)


@pytest.fixture(autouse=True)
def reset_limits() -> None:
    services.request_limiter.reset()


def account(nickname: str = "Sam") -> User:
    n = next(_names)
    return account_services.create_account(
        f"login_{n}",
        "correct horse battery",
        nickname,
        PLAYER_COLORS[2],
        Avatar("cutouts", f"s{n}"),
        {},
    )


def call(client: Client, method: str, path: str, user: User | None = None, body=None):
    headers = {"HTTP_AUTHORIZATION": f"Bearer {issue_token(user.pk)}"} if user else {}
    if method == "GET":
        return client.get(path, **headers)
    data = json.dumps(body) if body is not None else ""
    return getattr(client, method.lower())(
        path, data=data, content_type="application/json", **headers
    )


def tag(user: User) -> str:
    user.profile.refresh_from_db()
    return user.profile.tag


def request(client: Client, sender: User, target: User | str):
    return call(
        client,
        "POST",
        "/api/friends/requests",
        sender,
        {"tag": target if isinstance(target, str) else tag(target)},
    )


def overview(client: Client, user: User) -> dict[str, Any]:
    response = call(client, "GET", "/api/friends", user)
    assert response.status_code == 200
    return response.json()


def befriend(client: Client, a: User, b: User) -> None:
    assert request(client, a, b).json() == {"status": "requested"}
    assert request(client, b, a).json() == {"status": "friends"}


def error(response) -> str:
    return response.json()["error"]["code"]


# ----- auth and caching ------------------------------------------------------------------------

ENDPOINTS = [
    ("GET", "/api/friends"),
    ("POST", "/api/friends/requests"),
    ("POST", "/api/friends/requests/1/accept"),
    ("POST", "/api/friends/requests/1/decline"),
    ("DELETE", "/api/friends/requests/1"),
    ("DELETE", "/api/friends/ABCDEF"),
    ("GET", "/api/friends/ABCDEF/profile"),
    ("POST", "/api/blocks"),
    ("DELETE", "/api/blocks/ABCDEF"),
    ("POST", "/api/reports"),
    ("GET", "/api/me/settings"),
    ("PATCH", "/api/me/settings"),
]


@pytest.mark.parametrize(("method", "path"), ENDPOINTS)
def test_every_endpoint_needs_a_token_and_is_never_cached(client: Client, method, path) -> None:
    response = call(client, method, path, body={})
    assert response.status_code == 401 and error(response) == "UNAUTHORIZED"
    assert response["Cache-Control"] == "no-store"
    authed = call(client, method, path, account(), body={})
    assert authed.status_code != 401
    assert authed["Cache-Control"] == "no-store"


def test_disabled_accounts_cannot_use_any_endpoint(client: Client) -> None:
    user, other = account(), account()
    user.is_active = False
    user.save()
    assert request(client, user, other).status_code == 401
    assert call(client, "GET", "/api/friends", user).status_code == 401


def test_wrong_method_is_405(client: Client) -> None:
    user = account()
    assert call(client, "PUT", "/api/me/settings", user).status_code == 405
    assert call(client, "GET", "/api/friends/requests", user).status_code == 405


# ----- requests ---------------------------------------------------------------------------------


def test_empty_overview(client: Client) -> None:
    assert overview(client, account()) == {
        "friends": [],
        "incoming": [],
        "outgoing": [],
        "blocked": [],
    }


def test_request_and_accept(client: Client) -> None:
    ann, bob = account("Ann"), account("Bob")
    assert request(client, ann, f"  #{tag(bob).lower()} ").json() == {"status": "requested"}
    outgoing = overview(client, ann)["outgoing"]
    incoming = overview(client, bob)["incoming"]
    assert [r["nickname"] for r in outgoing] == ["Bob"] and outgoing[0]["tag"] == tag(bob)
    assert set(incoming[0]) == {"requestId", "tag", "nickname", "avatar", "color", "createdAt"}
    assert incoming[0]["tag"] == tag(ann) and incoming[0]["nickname"] == "Ann"
    assert incoming[0]["avatar"] == {"style": "cutouts", "seed": ann.profile.avatar_seed}
    request_id = incoming[0]["requestId"]
    # only the recipient may accept or decline
    assert (
        error(call(client, "POST", f"/api/friends/requests/{request_id}/accept", ann))
        == "NOT_FOUND"
    )
    assert (
        error(call(client, "POST", f"/api/friends/requests/{request_id}/decline", ann))
        == "NOT_FOUND"
    )
    response = call(client, "POST", f"/api/friends/requests/{request_id}/accept", bob)
    assert response.status_code == 200 and response.json() == {"status": "friends"}
    for me, other in ((ann, bob), (bob, ann)):
        data = overview(client, me)
        assert data["incoming"] == data["outgoing"] == []
        assert data["friends"] == [
            {
                "tag": tag(other),
                "nickname": other.profile.nickname,
                "avatar": {"style": "cutouts", "seed": other.profile.avatar_seed},
                "color": PLAYER_COLORS[2],
                "status": "offline",
            }
        ]


def test_request_errors(client: Client) -> None:
    ann, bob = account(), account()
    assert error(request(client, ann, "ZZZZZ")) == "INVALID_INPUT"
    assert error(call(client, "POST", "/api/friends/requests", ann, {"tag": 7})) == "INVALID_INPUT"
    missing = request(client, ann, "#ZZZZZZ")
    assert missing.status_code == 404 and error(missing) == "NOT_FOUND"
    assert error(request(client, ann, ann)) == "SELF"
    request(client, ann, bob)
    again = request(client, ann, bob)
    assert again.status_code == 409 and error(again) == "ALREADY_REQUESTED"
    request(client, bob, ann)
    assert error(request(client, ann, bob)) == "ALREADY_FRIENDS"


def test_crossed_requests_auto_accept(client: Client) -> None:
    ann, bob = account(), account()
    request(client, ann, bob)
    assert request(client, bob, ann).json() == {"status": "friends"}
    assert Friendship.objects.count() == 1 and FriendRequest.objects.count() == 0


def test_decline_and_cancel(client: Client) -> None:
    ann, bob = account(), account()
    request(client, ann, bob)
    rid = FriendRequest.objects.get().pk
    assert call(client, "POST", f"/api/friends/requests/{rid}/decline", bob).json() == {"ok": True}
    assert FriendRequest.objects.count() == 0 and Friendship.objects.count() == 0
    request(client, ann, bob)
    rid = FriendRequest.objects.get().pk
    assert error(call(client, "DELETE", f"/api/friends/requests/{rid}", bob)) == "NOT_FOUND"
    assert call(client, "DELETE", f"/api/friends/requests/{rid}", ann).json() == {"ok": True}
    assert FriendRequest.objects.count() == 0
    assert error(call(client, "POST", f"/api/friends/requests/{rid}/accept", bob)) == "NOT_FOUND"


def test_remove_friend_is_silent(client: Client) -> None:
    ann, bob = account(), account()
    befriend(client, ann, bob)
    assert call(client, "DELETE", f"/api/friends/{tag(bob)}", ann).json() == {"ok": True}
    assert overview(client, bob)["friends"] == []
    assert error(call(client, "DELETE", f"/api/friends/{tag(bob)}", ann)) == "NOT_FOUND"


def test_friend_and_pending_limits(client: Client, monkeypatch) -> None:
    monkeypatch.setattr(services, "MAX_PENDING_OUTGOING", 2)
    monkeypatch.setattr(services, "MAX_PENDING_INCOMING", 2)
    monkeypatch.setattr(services, "MAX_FRIENDS", 1)
    ann, others = account(), [account() for _ in range(3)]
    request(client, ann, others[0])
    request(client, ann, others[1])
    full = request(client, ann, others[2])
    assert full.status_code == 409 and error(full) == "LIMIT_REACHED"
    # the target's inbox is full
    target = account()
    request(client, others[0], target)
    request(client, others[1], target)
    assert error(request(client, others[2], target)) == "LIMIT_REACHED"
    # friends cap: ann already has one friend, so accepting a second fails
    request(client, others[0], ann)  # crossed: ann and others[0] become friends
    assert Friendship.objects.count() == 1
    assert error(request(client, others[1], ann)) == "LIMIT_REACHED"  # crossed but capped
    assert error(request(client, ann, account())) == "LIMIT_REACHED"


def test_requests_are_rate_limited_per_hour(client: Client, monkeypatch) -> None:
    monkeypatch.setattr(services.request_limiter, "limit", 3)
    ann = account()
    for _ in range(3):
        assert request(client, ann, account()).status_code == 200
    limited = request(client, ann, account())
    assert limited.status_code == 429 and error(limited) == "RATE_LIMITED"


# ----- blocks -----------------------------------------------------------------------------------


def test_requests_to_blocked_or_disabled_targets_look_normal(client: Client) -> None:
    ann, bob, cat, dan = account(), account(), account(), account()
    normal = request(client, ann, dan)
    call(client, "POST", "/api/blocks", bob, {"tag": tag(ann)})  # bob blocked ann
    call(client, "POST", "/api/blocks", ann, {"tag": tag(cat)})  # ann blocked cat
    dan_two = account()
    dan_two.is_active = False
    dan_two.save()
    for target in (bob, cat, dan_two):
        hidden = request(client, ann, target)
        assert (hidden.status_code, hidden.json()) == (normal.status_code, normal.json())
    assert list(FriendRequest.objects.values_list("to_user_id", flat=True)) == [dan.pk]
    # and the other direction: the blocker's target cannot reach them either
    assert request(client, bob, ann).json() == {"status": "requested"}
    assert FriendRequest.objects.count() == 1


def test_block_removes_friendship_and_requests_silently(client: Client) -> None:
    ann, bob, cat = account(), account(), account()
    befriend(client, ann, bob)
    request(client, cat, ann)
    request(client, ann, cat)  # crossed: friends
    dan = account()
    request(client, dan, ann)
    assert call(client, "POST", "/api/blocks", ann, {"tag": tag(bob)}).json() == {"ok": True}
    assert call(client, "POST", "/api/blocks", ann, {"tag": tag(dan)}).json() == {"ok": True}
    assert Friendship.objects.count() == 1  # ann and cat only
    assert FriendRequest.objects.count() == 0
    mine = overview(client, ann)
    assert [f["tag"] for f in mine["friends"]] == [tag(cat)]
    assert {b["tag"] for b in mine["blocked"]} == {tag(bob), tag(dan)}
    assert set(mine["blocked"][0]) == {"tag", "nickname", "avatar", "color"}
    theirs = overview(client, bob)
    assert theirs == {"friends": [], "incoming": [], "outgoing": [], "blocked": []}
    # blocking twice is fine; self and unknown are errors
    assert call(client, "POST", "/api/blocks", ann, {"tag": tag(bob)}).status_code == 200
    assert error(call(client, "POST", "/api/blocks", ann, {"tag": tag(ann)})) == "SELF"
    assert error(call(client, "POST", "/api/blocks", ann, {"tag": "ZZZZZZ"})) == "NOT_FOUND"


def test_unblock(client: Client) -> None:
    ann, bob = account(), account()
    call(client, "POST", "/api/blocks", ann, {"tag": tag(bob)})
    assert call(client, "DELETE", f"/api/blocks/{tag(bob)}", ann).json() == {"ok": True}
    assert Block.objects.count() == 0
    assert error(call(client, "DELETE", f"/api/blocks/{tag(bob)}", ann)) == "NOT_FOUND"
    befriend(client, ann, bob)  # requests work again


# ----- friend profile ---------------------------------------------------------------------------


def test_friend_profile_only_for_friends(client: Client) -> None:
    ann, bob, cat = account("Ann"), account("Bob"), account("Cat")
    PlayerStats.objects.create(user=bob, game_id="rps", played=6, wins=4)
    befriend(client, ann, bob)
    response = call(client, "GET", f"/api/friends/{tag(bob)}/profile", ann)
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"tag", "nickname", "avatar", "color", "memberSince", "stats"}
    assert data["nickname"] == "Bob" and data["tag"] == tag(bob)
    mine = call(client, "GET", "/api/me/stats", bob).json()
    assert data["stats"] == mine and data["stats"]["totals"]["wins"] == 4
    for path in (f"/api/friends/{tag(cat)}/profile", "/api/friends/ZZZZZZ/profile"):
        denied = call(client, "GET", path, ann)
        assert denied.status_code == 403 and "stats" not in denied.json()
    call(client, "DELETE", f"/api/friends/{tag(bob)}", ann)
    assert call(client, "GET", f"/api/friends/{tag(bob)}/profile", ann).status_code == 403


# ----- reports ----------------------------------------------------------------------------------


def report(client: Client, user: User, target: User | str, reason="spam", note=None):
    body: dict[str, Any] = {
        "tag": target if isinstance(target, str) else tag(target),
        "reason": reason,
    }
    if note is not None:
        body["note"] = note
    return call(client, "POST", "/api/reports", user, body)


def test_report_validation(client: Client) -> None:
    ann, bob = account(), account("Bob")
    assert error(report(client, ann, bob, reason="rude")) == "INVALID_INPUT"
    assert error(report(client, ann, bob, note=5)) == "INVALID_INPUT"
    long = report(client, ann, bob, note="x" * (REPORT_NOTE_MAX + 1))
    assert long.status_code == 400 and "note" in long.json()["error"]["fields"]
    assert error(report(client, ann, ann)) == "SELF"
    assert error(report(client, ann, "ZZZZZZ")) == "NOT_FOUND"
    assert Report.objects.count() == 0
    for reason in REPORT_REASONS:
        assert report(client, ann, account(), reason=reason).json() == {"ok": True}


def test_report_stores_a_clean_note_and_snapshot(client: Client) -> None:
    ann, bob = account("Ann"), account("Bob")
    note = "line one\nline\x00 two‮ \x1b[31m" + "y" * 10
    assert report(client, ann, bob, reason="harassment", note=note).status_code == 200
    stored = Report.objects.get()
    assert stored.note == "line one line two [31m" + "y" * 10
    assert stored.reporter == ann and stored.reported_user == bob
    assert stored.reported_nickname == "Bob" and stored.status == "open"
    assert stored.reason == "harassment" and stored.reported_guest_key == ""


def test_duplicate_reports_merge(client: Client) -> None:
    ann, bob = account(), account()
    report(client, ann, bob)
    assert report(client, ann, bob, reason="cheating", note="later note").json() == {"ok": True}
    stored = Report.objects.get()
    assert stored.note == "later note" and stored.reason == "spam"
    # outside the window, or once handled, a new report is created
    Report.objects.update(created_at=timezone.now() - timedelta(hours=25))
    report(client, ann, bob)
    assert Report.objects.count() == 2
    Report.objects.update(status="dismissed")
    report(client, ann, bob)
    assert Report.objects.count() == 3


def test_reports_per_day(client: Client) -> None:
    ann = account()
    targets = [account() for _ in range(REPORTS_PER_DAY + 1)]
    for target in targets[:REPORTS_PER_DAY]:
        assert report(client, ann, target).status_code == 200
    limited = report(client, ann, targets[-1])
    assert limited.status_code == 429 and error(limited) == "RATE_LIMITED"
    assert report(client, ann, targets[0]).status_code == 200  # merging still works
    Report.objects.update(created_at=timezone.now() - timedelta(days=2))
    assert report(client, ann, targets[-1]).status_code == 200


# ----- settings ---------------------------------------------------------------------------------


def test_presence_setting(client: Client) -> None:
    ann = account()
    assert call(client, "GET", "/api/me/settings", ann).json() == {"presence": "online"}
    for mode in ("busy", "offline", "online"):
        response = call(client, "PATCH", "/api/me/settings", ann, {"presence": mode})
        assert response.json() == {"presence": mode}
        ann.profile.refresh_from_db()
        assert ann.profile.presence_mode == mode
    bad = call(client, "PATCH", "/api/me/settings", ann, {"presence": "away"})
    assert bad.status_code == 400 and "presence" in bad.json()["error"]["fields"]


# ----- recent players ---------------------------------------------------------------------------


def test_recent_players_relationship_and_block_exclusions(client: Client) -> None:
    me, friend, asked, asker, stranger, blocked, blocker = (account(n) for n in "ABCDEFG")
    session([me, friend, asked, asker, stranger, blocked, blocker])
    befriend(client, me, friend)
    request(client, me, asked)
    request(client, asker, me)
    call(client, "POST", "/api/blocks", me, {"tag": tag(blocked)})
    call(client, "POST", "/api/blocks", blocker, {"tag": tag(me)})
    players = call(client, "GET", "/api/me/recent-players", me).json()["players"]
    assert {p["nickname"]: p["relationship"] for p in players} == {
        "B": "friends",
        "C": "requested",
        "D": "incoming",
        "E": "none",
    }
    theirs = call(client, "GET", "/api/me/recent-players", blocker).json()["players"]
    assert "A" not in {p["nickname"] for p in theirs}


# ----- deletion and disabling -------------------------------------------------------------------


def test_deleting_an_account_cleans_up_but_keeps_reports(client: Client) -> None:
    ann, bob, cat = account("Ann"), account("Bob"), account("Cat")
    befriend(client, ann, bob)
    request(client, ann, cat)
    call(client, "POST", "/api/blocks", cat, {"tag": tag(bob)})
    report(client, cat, ann, note="about ann")
    report(client, ann, cat)
    account_services.delete_account(ann)
    assert Friendship.objects.count() == 0 and FriendRequest.objects.count() == 0
    assert Block.objects.count() == 1  # cat -> bob is unrelated
    about = Report.objects.get(note="about ann")
    assert about.reported_user is None and about.reported_nickname == "Ann"
    by = Report.objects.exclude(pk=about.pk).get()
    assert by.reporter is None and by.reported_user == cat
    account_services.delete_account(cat)
    assert Block.objects.count() == 0 and Report.objects.count() == 2


def test_disabled_accounts_drop_out_of_lists(client: Client) -> None:
    ann, bob, cat = account(), account(), account()
    befriend(client, ann, bob)
    request(client, cat, ann)
    for user in (bob, cat):
        user.is_active = False
        user.save()
    data = overview(client, ann)
    assert data["friends"] == [] and data["incoming"] == []
    rid = FriendRequest.objects.get().pk
    assert error(call(client, "POST", f"/api/friends/requests/{rid}/accept", ann)) == "NOT_FOUND"
    assert call(client, "GET", f"/api/friends/{tag(bob)}/profile", ann).status_code == 403
    bob.is_active = True
    bob.save()
    assert [f["tag"] for f in overview(client, ann)["friends"]] == [tag(bob)]


# ----- privacy ----------------------------------------------------------------------------------


def test_no_username_id_or_email_in_any_payload(client: Client) -> None:
    ann, bob, cat = account("Ann"), account("Bob"), account("Cat")
    for u in (ann, bob, cat):
        u.email = f"{u.username}@example.com"
        u.save()
    befriend(client, ann, bob)
    request(client, cat, ann)
    call(client, "POST", "/api/blocks", ann, {"tag": tag(account("Dan"))})
    session([ann, bob, cat])
    bodies = [
        call(client, "GET", "/api/friends", ann).content,
        call(client, "GET", f"/api/friends/{tag(bob)}/profile", ann).content,
        call(client, "GET", "/api/me/recent-players", ann).content,
        call(client, "GET", "/api/me/settings", ann).content,
        request(client, ann, account()).content,
        report(client, ann, cat).content,
    ]
    for body in bodies:
        text = body.decode()
        for u in (ann, bob, cat):
            assert u.username not in text and u.email not in text
        data = json.loads(text)
        keys = set(_keys(data))
        assert not keys & {"id", "userId", "user_id", "username", "email", "profileId", "guestKey"}


def _keys(value: Any):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _keys(v)
    elif isinstance(value, list):
        for v in value:
            yield from _keys(v)
