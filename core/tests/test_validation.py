"""Unit tests for request parsing, profile sanitizing, nickname suffixes and rate limiting."""

import json

import pytest

from games.constants import ACTION_RATE_LIMIT_PER_SEC, PLAYER_COLORS
from rooms.models_types import RoomError
from rooms.validation import (
    BadMessage,
    RateLimiter,
    normalize_code,
    optional_token,
    parse_request,
    unique_nickname,
    validate_profile,
)
from tests.conftest import make_profile


def test_parse_valid_request() -> None:
    req = parse_request(json.dumps({"id": 3, "type": "room:peek", "payload": {"code": "ABCD"}}))
    assert (req.id, req.type, req.payload) == (3, "room:peek", {"code": "ABCD"})


@pytest.mark.parametrize(
    ("text", "request_id"),
    [
        (None, None),
        ("not json", None),
        ("[1,2]", None),
        ('{"type":"room:peek","payload":{}}', None),
        ('{"id":true,"type":"room:peek","payload":{}}', None),
        ('{"id":"1","type":"room:peek","payload":{}}', None),
        ('{"id":4,"type":5,"payload":{}}', 4),
        ('{"id":4,"type":"room:peek"}', 4),
        ('{"id":4,"type":"room:peek","payload":[]}', 4),
        ("x" * 9000, None),
    ],
)
def test_parse_bad_messages(text: str | None, request_id: int | None) -> None:
    with pytest.raises(BadMessage) as exc:
        parse_request(text)
    assert exc.value.request_id == request_id


def test_profile_is_trimmed_and_stats_ignored() -> None:
    raw = make_profile("  Sam  ", color=PLAYER_COLORS[2].lower(), stats={"wins": 999})
    profile = validate_profile(raw)
    assert profile.nickname == "Sam"
    assert profile.color == PLAYER_COLORS[2]
    assert not hasattr(profile, "stats")


@pytest.mark.parametrize(
    "overrides",
    [
        {"nickname": ""},
        {"nickname": "   "},
        {"nickname": "x" * 13},
        {"nickname": "<script>"},
        {"nickname": 42},
        {"emoji": "💩"},
        {"color": "#000000"},
        {"color": None},
        {"id": ""},
        {"id": "x" * 65},
    ],
)
def test_invalid_profiles(overrides: dict) -> None:
    with pytest.raises(RoomError) as exc:
        validate_profile(make_profile(**overrides))
    assert exc.value.code == "INVALID_ACTION"


def test_profile_must_be_object() -> None:
    with pytest.raises(RoomError):
        validate_profile("Sam")


def test_nickname_length_bounds() -> None:
    assert validate_profile(make_profile("A")).nickname == "A"
    assert validate_profile(make_profile("x" * 12)).nickname == "x" * 12


def test_unique_nickname_suffixes() -> None:
    assert unique_nickname("Sam", []) == "Sam"
    assert unique_nickname("Sam", ["Sam"]) == "Sam2"
    assert unique_nickname("sam", ["Sam", "SAM2"]) == "sam3"
    assert unique_nickname("Alexandrinas", ["Alexandrinas"]) == "Alexandrina2"
    taken = ["x" * 12] + [f"{'x' * 11}{n}" for n in range(2, 10)]
    assert unique_nickname("x" * 12, taken) == "x" * 10 + "10"


def test_normalize_code() -> None:
    assert normalize_code(" abcd ") == "ABCD"
    for bad in ["ABC", "ABCDE", "ABCO", "AB1D", None]:
        with pytest.raises(RoomError) as exc:
            normalize_code(bad)
        assert exc.value.code == "ROOM_NOT_FOUND"


def test_optional_token() -> None:
    assert optional_token(None) is None
    assert optional_token("abc") == "abc"
    with pytest.raises(RoomError):
        optional_token(5)


def test_rate_limiter_sliding_window() -> None:
    now = [0.0]
    limiter = RateLimiter(clock=lambda: now[0])
    assert all(limiter.allow() for _ in range(ACTION_RATE_LIMIT_PER_SEC))
    assert not limiter.allow()
    now[0] = 0.999
    assert not limiter.allow()
    now[0] = 1.0
    assert limiter.allow()
