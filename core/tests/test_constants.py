"""Shared constants: presence and values from implementation plan section 1.4."""

import json
import re

from games import constants as c

PLAN_1_4 = {
    "ROOM_CODE_LENGTH": 4,
    "ROOM_CODE_ALPHABET": "ABCDEFGHJKLMNPQRSTUVWXYZ",
    "MAX_PLAYERS": 10,
    "NICKNAME_MIN": 1,
    "NICKNAME_MAX": 12,
    "ROOM_IDLE_TTL_MS": 2 * 60 * 60 * 1000,
    "OFFLINE_FORFEIT_MS": 30_000,
    "ACTION_RATE_LIMIT_PER_SEC": 5,
    "RPS_PICK_TIMEOUT_MS": 10_000,
    "GUESS_ROUND_MS": 30_000,
    "GUESS_HINT1_MS": 10_000,
    "GUESS_HINT2_MS": 20_000,
    "DICE_TURN_MS": 30_000,
    "NAMEIT_TURN_MS": 10_000,
    "NAMEIT_CHALLENGE_WINDOW_MS": 5_000,
    "NAMEIT_VOTE_MS": 8_000,
}


def test_plan_constants_match_json_and_module() -> None:
    raw = json.loads(c.CONSTANTS_PATH.read_text(encoding="utf-8"))
    for name, value in PLAN_1_4.items():
        assert raw[name] == value, name
        assert getattr(c, name) == value, name


def test_every_json_key_is_exposed() -> None:
    raw = json.loads(c.CONSTANTS_PATH.read_text(encoding="utf-8"))
    for name in raw:
        assert hasattr(c, name), name


def test_alphabet_excludes_confusing_letters() -> None:
    assert "I" not in c.ROOM_CODE_ALPHABET
    assert "O" not in c.ROOM_CODE_ALPHABET
    assert len(set(c.ROOM_CODE_ALPHABET)) == len(c.ROOM_CODE_ALPHABET) == 24


def test_avatar_constants() -> None:
    raw = json.loads(c.CONSTANTS_PATH.read_text(encoding="utf-8"))
    assert "EMOJI_PRESETS" not in raw
    assert c.AVATAR_API_VERSION == "10.x"
    assert c.AVATAR_STYLES == ("adventurer-neutral", "croodles-neutral", "cutouts", "voxel-art")
    seed = re.compile(c.AVATAR_SEED_PATTERN)
    for ok in ["a", "9c41e07b", "A_b-C", "x" * 32]:
        assert seed.fullmatch(ok), ok
    for bad in ["", "x" * 33, "a b", "a/b", "é"]:
        assert not seed.fullmatch(bad), bad


def test_player_colors_are_10_unique_hex() -> None:
    assert len(c.PLAYER_COLORS) == 10
    assert len({color.upper() for color in c.PLAYER_COLORS}) == 10
    for color in c.PLAYER_COLORS:
        assert re.fullmatch(r"#[0-9A-F]{6}", color), color


def test_nickname_pattern() -> None:
    pattern = re.compile(c.NICKNAME_ALLOWED_PATTERN)
    for ok in ["Sam", "Mary Jo", "J.R.", "Al-Amin", "x_9", "Rock&Roll", "Who?"]:
        assert pattern.fullmatch(ok), ok
    for bad in ["<b>", "a/b", "émile", "tab\tname", "😀"]:
        assert not pattern.fullmatch(bad), bad


def test_dots_turn_timer_matches_plan_section_10() -> None:
    assert c.DOTS_TURN_MS == 45_000


def test_account_constants() -> None:
    assert c.PASSWORD_MIN_LENGTH == 8
    assert c.AUTH_TOKEN_DAYS == 30
    assert c.AUTH_RATE_LIMIT_PER_MIN == 10
    assert c.STATS_MAX_IMPORT_GAMES == 500
    username = re.compile(c.USERNAME_PATTERN)
    for ok in ["sam", "Sam_99", "x" * 20]:
        assert username.fullmatch(ok), ok
    for bad in ["ab", "x" * 21, "sam smith", "sam-1", "é" * 3]:
        assert not username.fullmatch(bad), bad


def test_dashboard_constants() -> None:
    assert c.ACTIVITY_RETENTION_DAYS == 180
    assert c.DASHBOARD_MIN_GAMES_FOR_RATES == 5
    assert c.DASHBOARD_PAGE_SIZE == 50
    assert c.GUEST_KEY_LENGTH == 16
    assert c.ADMIN_LOGIN_MAX_FAILS == 5
    assert c.ADMIN_LOGIN_LOCK_MINUTES == 15
