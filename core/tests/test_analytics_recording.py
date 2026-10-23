"""Activity recording: sessions, participations, events, guest keys, deletion, retention."""

import asyncio
import json
import logging
from datetime import timedelta

import pytest
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.core import serializers
from django.test import Client
from django.utils import timezone

from accounts import services
from accounts.models import Profile
from accounts.tokens import issue_token
from analytics import recorder as recorder_module
from analytics.keys import guest_key
from analytics.models import DELETED_NICKNAME, ActivityEvent, GameParticipation, GameSession
from analytics.recorder import Recorder, SeatRecord, SessionRecord, write_record
from analytics.retention import prune_events
from games.constants import ACTIVITY_RETENTION_DAYS, GUEST_KEY_LENGTH, PLAYER_COLORS
from rooms import hooks
from tests.conftest import make_profile
from tests.dummy_game import SECRET

PASSWORD = "correct horse battery"


@database_sync_to_async
def make_account(username: str = "sam_1") -> tuple[User, str]:
    user = User.objects.create_user(username=username, password=PASSWORD)
    Profile.objects.create(
        user=user,
        nickname="Saved",
        color=PLAYER_COLORS[4],
        avatar_style="cutouts",
        avatar_seed="s1",
    )
    return user, issue_token(user.pk)


@database_sync_to_async
def db(fn):
    return fn()


def kinds() -> list[str]:
    return list(ActivityEvent.objects.order_by("id").values_list("kind", flat=True))


async def seat_room(connect, names, host_token=None, settings=None):
    """Create a room (host first), seat `names`, select the dummy game. Returns clients."""
    clients = []
    host = await connect()
    payload = {"profile": make_profile(names[0])}
    if host_token:
        payload["authToken"] = host_token
    ack = await host.request("room:create", payload)
    code = ack["data"]["room"]["code"]
    clients.append(host)
    for name in names[1:]:
        client = await connect()
        assert (await client.request("room:join", {"code": code, "profile": make_profile(name)}))[
            "ok"
        ]
        clients.append(client)
    ack = await host.request("room:selectGame", {"gameId": "dummy", "settings": settings or {}})
    assert ack["ok"], ack
    return code, clients


async def start(clients):
    assert (await clients[0].request("game:start"))["ok"]
    for client in clients:
        await client.wait_push("game:view")


# Guest keys


def test_guest_key_is_a_short_keyed_hash() -> None:
    key = guest_key("prof-Sam")
    assert len(key) == GUEST_KEY_LENGTH and int(key, 16) >= 0
    assert key == guest_key("prof-Sam")
    assert key != guest_key("prof-Ann")
    assert "prof-Sam" not in key


def test_guest_key_depends_on_secret_key(settings) -> None:
    before = guest_key("prof-Sam")
    settings.SECRET_KEY = "another-secret-key-that-is-long-enough-for-hmac"
    assert guest_key("prof-Sam") != before


# Completed, abandoned and forfeited games (through the real WebSocket flow)


@pytest.mark.django_db(transaction=True)
async def test_completed_game_records_session_participations_and_events(connect, recording) -> None:
    user, token = await make_account()
    code, (host, ann) = await seat_room(
        connect, ["Host", "Ann"], host_token=token, settings={"target": 1}
    )
    await start([host, ann])
    assert (await host.request("game:action", {"type": "score"}))["ok"]
    await ann.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    await hooks.drain()

    session = await db(lambda: GameSession.objects.get())
    assert session.status == "completed" and session.game_id == "dummy"
    assert session.room_code == code and session.player_count == 2
    assert session.settings == {"target": 1, "turnMs": 10_000}
    assert session.ended_at >= session.started_at
    rows = await db(
        lambda: {
            p.nickname: p
            for p in GameParticipation.objects.filter(session=session).select_related("user")
        }
    )
    saved, guest = rows["Saved"], rows["Ann"]
    assert saved.user_id == user.pk and saved.guest_key == "" and saved.player_type == "registered"
    assert saved.placement == 1 and saved.is_win and saved.session_points == 100
    assert saved.raw_score == 1 and not saved.left_early
    assert guest.user_id is None and guest.player_type == "guest"
    assert guest.guest_key == guest_key("prof-Ann")
    assert guest.placement == 2 and not guest.is_win and guest.session_points == 0
    assert await db(kinds) == [
        "room_created",
        "room_joined",
        "game_started",
        "game_finished",
    ]
    events = await db(lambda: list(ActivityEvent.objects.order_by("id")))
    assert events[0].user_id == user.pk and events[0].guest_key == ""
    assert events[1].user_id is None and events[1].guest_key == guest_key("prof-Ann")
    assert events[3].meta == {"players": 2, "seconds": events[3].meta["seconds"]}


@pytest.mark.django_db(transaction=True)
async def test_raw_profile_ids_and_secrets_never_stored(connect, recording) -> None:
    _, token = await make_account()
    code, (host, ann) = await seat_room(
        connect, ["Host", "Ann"], host_token=token, settings={"target": 1}
    )
    await start([host, ann])
    await host.request("game:action", {"type": "score"})
    await ann.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    await hooks.drain()
    dumped = await db(
        lambda: serializers.serialize(
            "json",
            [
                *GameSession.objects.all(),
                *GameParticipation.objects.all(),
                *ActivityEvent.objects.all(),
            ],
        )
    )
    for secret in ["prof-Ann", "prof-Host", token, ann.token, host.token, PASSWORD, SECRET]:
        assert secret not in dumped


@pytest.mark.django_db(transaction=True)
async def test_forfeit_counts_as_left_early_loss(connect, recording) -> None:
    code, (host, ann, bob) = await seat_room(
        connect, ["Host", "Ann", "Bob"], settings={"target": 2, "turnMs": 150}
    )
    await start([host, ann, bob])
    await host.request("game:action", {"type": "score"})
    await ann.request("game:action", {"type": "score"})
    assert (await bob.request("room:leave"))["ok"]
    await host.wait_push("game:event", lambda d: d["kind"] == "timeout", timeout=3)
    assert (await host.request("game:action", {"type": "score"}))["ok"]
    await ann.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    await hooks.drain()
    rows = await db(lambda: {p.nickname: p for p in GameParticipation.objects.all()})
    assert rows["Bob"].left_early and rows["Bob"].placement == 3 and not rows["Bob"].is_win
    assert rows["Host"].is_win and not rows["Host"].left_early
    assert await db(lambda: GameSession.objects.get().status) == "completed"
    assert "room_left" in await db(kinds)


@pytest.mark.django_db(transaction=True)
async def test_everyone_leaving_mid_game_records_abandoned(connect, recording) -> None:
    code, (host, ann) = await seat_room(connect, ["Host", "Ann"])
    await start([host, ann])
    assert (await ann.request("room:leave"))["ok"]
    assert (await host.request("room:leave"))["ok"]
    await hooks.drain()
    session = await db(lambda: GameSession.objects.get())
    assert session.status == "abandoned"
    parts = await db(lambda: list(GameParticipation.objects.all()))
    assert len(parts) == 2
    assert all(p.placement is None and not p.is_win and p.session_points is None for p in parts)
    assert all(p.left_early for p in parts)
    assert (await db(kinds))[-1] == "game_abandoned"


@pytest.mark.django_db(transaction=True)
async def test_idle_cleanup_mid_game_records_abandoned(connect, manager, recording) -> None:
    code, (host, ann) = await seat_room(connect, ["Host", "Ann"])
    await start([host, ann])
    manager.idle_ttl_ms = -1
    assert await manager.cleanup() == [code]
    await hooks.drain()
    assert await db(lambda: GameSession.objects.get().status) == "abandoned"


@pytest.mark.django_db(transaction=True)
async def test_lobby_room_removal_records_no_session(connect, recording) -> None:
    code, (host, ann) = await seat_room(connect, ["Host", "Ann"])
    await ann.request("room:leave")
    await host.request("room:leave")
    await hooks.drain()
    assert not await db(lambda: GameSession.objects.exists())


@pytest.mark.django_db(transaction=True)
async def test_seat_reclaim_is_not_a_new_join(connect, recording) -> None:
    code, (host, ann) = await seat_room(connect, ["Host", "Ann"])
    again = await connect()
    ack = await again.request(
        "room:join", {"code": code, "profile": make_profile("Ann"), "roomToken": ann.token}
    )
    assert ack["ok"]
    await hooks.drain()
    assert (await db(kinds)).count("room_joined") == 1


# Records written directly: ties, deleted accounts


def session(seats, status="completed") -> SessionRecord:
    return SessionRecord("rps", "ABCD", {}, status, 1_000_000.0, 1_065_400.0, tuple(seats))


@pytest.mark.django_db
def test_ties_share_the_win() -> None:
    write_record(
        session(
            [
                SeatRecord(None, "g1", "A", False, placement=1, raw_score=3, points=75),
                SeatRecord(None, "g2", "B", False, placement=1, raw_score=3, points=75),
                SeatRecord(None, "g3", "C", False, placement=3, raw_score=1, points=0),
            ]
        )
    )
    wins = dict(GameParticipation.objects.values_list("nickname", "is_win"))
    assert wins == {"A": True, "B": True, "C": False}
    assert GameSession.objects.get().duration_seconds == 65


@pytest.mark.django_db
def test_abandoned_record_never_has_placements_or_wins() -> None:
    write_record(session([SeatRecord(None, "g1", "A", True, placement=1, points=100)], "abandoned"))
    part = GameParticipation.objects.get()
    assert part.placement is None and not part.is_win and part.session_points is None


@pytest.mark.django_db
def test_records_for_deleted_accounts_are_kept_without_the_user() -> None:
    write_record(session([SeatRecord(987, "", "Gone", False, placement=1, points=100)]))
    part = GameParticipation.objects.get()
    assert part.user_id is None and part.player_type == "registered" and part.is_win
    recorder_module.write_record(
        recorder_module.EventRecord("room_joined", timezone.now(), user_id=987)
    )
    assert ActivityEvent.objects.get().user_id is None


# Recorder behaviour


async def test_queue_full_drops_and_logs(caplog) -> None:
    rec = Recorder(maxsize=1)
    rec._queue = asyncio.Queue(maxsize=1)
    caplog.set_level(logging.WARNING, logger="analytics")
    rec._put(recorder_module.EventRecord("login", timezone.now()))
    rec._put(recorder_module.EventRecord("login", timezone.now()))
    assert rec.dropped == 1 and rec._queue.qsize() == 1
    assert "queue full" in caplog.text


async def test_record_calls_never_raise(caplog) -> None:
    rec = Recorder()
    rec.record_event("login", meta="not a dict")  # type: ignore[arg-type]
    rec.record_session(None)  # type: ignore[arg-type]
    assert "Could not queue" in caplog.text
    rec.stop()


async def test_record_returns_before_the_write(monkeypatch) -> None:
    written = []
    monkeypatch.setattr(recorder_module, "write_record", written.append)
    rec = Recorder()
    rec.record_event("login", user_id=None)
    assert written == []  # queued, not written inline
    await rec.drain()
    assert [r.kind for r in written] == ["login"]
    rec.stop()


@pytest.mark.django_db(transaction=True)
async def test_write_failure_does_not_break_the_game(connect, recording, monkeypatch, caplog):
    def broken(record):
        raise RuntimeError("database is down")

    monkeypatch.setattr(recorder_module, "write_record", broken)
    caplog.set_level(logging.ERROR, logger="analytics")
    code, (host, ann) = await seat_room(connect, ["Host", "Ann"], settings={"target": 1})
    await start([host, ann])
    await host.request("game:action", {"type": "score"})
    await ann.wait_push("game:event", lambda d: d["kind"] == "gameOver")
    state = await ann.wait_push("room:state", lambda d: d["status"] == "finished")
    assert state["wins"] == {host.player_id: 1}
    await hooks.drain()
    assert "Activity write failed" in caplog.text
    assert (await host.request("game:playAgain"))["ok"]


# Accounts: events and deletion


@pytest.mark.django_db
def test_signup_login_and_failed_login_events(client: Client, recording) -> None:
    from accounts import ratelimit

    ratelimit.register_limiter.reset()
    ratelimit.login_limiter.reset()
    body = {
        "username": "sam_1",
        "password": PASSWORD,
        "profile": {"nickname": "Sam", "color": PLAYER_COLORS[0]},
    }
    client.post("/api/auth/register", json.dumps(body), content_type="application/json")
    client.post(
        "/api/auth/login",
        json.dumps({"username": "sam_1", "password": PASSWORD}),
        content_type="application/json",
    )
    client.post(
        "/api/auth/login",
        json.dumps({"username": "who_is_this", "password": "wrong-password"}),
        content_type="application/json",
    )
    events = list(ActivityEvent.objects.order_by("id"))
    assert [e.kind for e in events] == ["signup", "login", "login_failed"]
    user = User.objects.get()
    assert events[0].user == user and events[1].user == user
    assert events[2].user is None and events[2].meta == {}
    dumped = serializers.serialize("json", events)
    assert "who_is_this" not in dumped and "wrong-password" not in dumped


@pytest.mark.django_db
def test_account_deletion_anonymises_and_keeps_totals(recording) -> None:
    user = User.objects.create_user(username="sam_1", password=PASSWORD)
    Profile.objects.create(
        user=user, nickname="Sam", color=PLAYER_COLORS[0], avatar_style="cutouts", avatar_seed="a"
    )
    write_record(
        session(
            [
                SeatRecord(user.pk, "", "Sam", False, placement=1, points=100),
                SeatRecord(None, "g2", "Ann", False, placement=2, points=0),
            ]
        )
    )
    ActivityEvent.objects.create(kind="login", occurred_at=timezone.now(), user=user)
    services.delete_account(user)
    assert not User.objects.exists()
    assert GameSession.objects.count() == 1
    assert GameParticipation.objects.count() == 2
    gone = GameParticipation.objects.get(is_win=True)
    assert gone.user_id is None and gone.nickname == DELETED_NICKNAME
    assert GameParticipation.objects.get(is_win=False).nickname == "Ann"
    assert not ActivityEvent.objects.filter(user__isnull=False).exists()
    assert list(ActivityEvent.objects.order_by("id").values_list("kind", flat=True)) == [
        "login",
        "account_deleted",
    ]


# Retention


@pytest.mark.django_db
def test_retention_prunes_only_old_events() -> None:
    now = timezone.now()
    old = now - timedelta(days=ACTIVITY_RETENTION_DAYS, minutes=1)
    recent = now - timedelta(days=ACTIVITY_RETENTION_DAYS - 1)
    ActivityEvent.objects.create(kind="login", occurred_at=old)
    ActivityEvent.objects.create(kind="signup", occurred_at=recent)
    write_record(session([SeatRecord(None, "g", "A", False, placement=1, points=100)]))
    GameSession.objects.update(started_at=old, ended_at=old)
    assert prune_events(now) == 1
    assert list(ActivityEvent.objects.values_list("kind", flat=True)) == ["signup"]
    assert GameSession.objects.count() == 1 and GameParticipation.objects.count() == 1


@pytest.mark.django_db(transaction=True)
async def test_retention_runs_when_the_recorder_starts(recording) -> None:
    old = timezone.now() - timedelta(days=ACTIVITY_RETENTION_DAYS + 1)
    await db(lambda: ActivityEvent.objects.create(kind="login", occurred_at=old))
    recording.start()
    for _ in range(50):
        if not await db(lambda: ActivityEvent.objects.exists()):
            break
        await asyncio.sleep(0.02)
    assert not await db(lambda: ActivityEvent.objects.exists())
