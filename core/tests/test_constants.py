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


def test_emoji_presets_are_24_unique() -> None:
    assert len(c.EMOJI_PRESETS) == 24
    assert len(set(c.EMOJI_PRESETS)) == 24


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
