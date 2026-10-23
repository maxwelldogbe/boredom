"""Seeded dashboard data shared by the dashboard and admin API tests (a pytest plugin)."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone

from accounts.models import Profile
from analytics.lockout import admin_lockout
from analytics.models import ActivityEvent
from analytics.recorder import SeatRecord, SessionRecord, write_record
from games.constants import PLAYER_COLORS

PASSWORD = "correct horse battery"
GUEST_CARL = "c" * 16
GUEST_DANA = "d" * 16


@pytest.fixture
def fresh_state():
    cache.clear()
    admin_lockout.reset()
    yield
    cache.clear()


def account(username: str, nickname: str, **extra) -> User:
    user = User.objects.create_user(username=username, password=PASSWORD, **extra)
    Profile.objects.create(
        user=user,
        nickname=nickname,
        color=PLAYER_COLORS[0],
        avatar_style="cutouts",
        avatar_seed="a",
    )
    return user


def play(game: str, seats, *, status: str = "completed", days_ago: float = 0, seconds: int = 60):
    """seats: [(user or guest key, nickname, placement)]."""
    start = timezone.now() - timedelta(days=days_ago)
    start_ms = start.timestamp() * 1000
    records = []
    for who, nickname, placement in seats:
        user_id = who.pk if isinstance(who, User) else None
        key = "" if user_id else who
        records.append(
            SeatRecord(user_id, key, nickname, False, placement=placement, raw_score=1, points=50)
        )
    write_record(
        SessionRecord(
            game, "ABCD", {"k": 1}, status, start_ms, start_ms + seconds * 1000, tuple(records)
        )
    )


@pytest.fixture
def world():
    """Two accounts, two guests and a known set of games.

    rps: Alice beats Carl 4 times, Carl beats Alice twice (6 games each).
    hangman: Alice and Bob tie for 1st once; Bob beats Alice twice.
    One abandoned rps game with Dana.
    """
    alice = account("alice", "Alice")
    bob = account("bob", "Bob")
    for i in range(6):
        alice_wins = i < 4
        play(
            "rps",
            [
                (alice, "Alice", 1 if alice_wins else 2),
                (GUEST_CARL, "Carl", 2 if alice_wins else 1),
            ],
            days_ago=i * 0.1,
        )
    play("hangman", [(alice, "Alice", 1), (bob, "Bob", 1)], days_ago=1, seconds=120)
    for _ in range(2):
        play("hangman", [(alice, "Alice", 2), (bob, "Bob", 1)], days_ago=2, seconds=120)
    play("rps", [(GUEST_DANA, "Dana", None), (alice, "Alice", None)], status="abandoned")
    now = timezone.now()
    ActivityEvent.objects.create(kind="login", occurred_at=now, user=alice)
    ActivityEvent.objects.create(kind="room_joined", occurred_at=now, guest_key=GUEST_CARL)
    ActivityEvent.objects.create(
        kind="room_joined", occurred_at=now - timedelta(days=3), guest_key=GUEST_DANA
    )
    return {"alice": alice, "bob": bob}
