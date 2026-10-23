"""Shared constants loaded from <repo>/shared/constants.json.

That JSON file is the single source of truth for the client and the server.
Never hardcode these values elsewhere; import them from here.
"""

import json
from pathlib import Path
from typing import Any

CONSTANTS_PATH = Path(__file__).resolve().parents[2] / "shared" / "constants.json"


def _load(path: Path) -> dict[str, Any]:
    """Read the constants file, failing loudly with the path if it is missing or invalid."""
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot load shared constants from {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Shared constants in {path} must be a JSON object.")
    return data


_C = _load(CONSTANTS_PATH)

ROOM_CODE_LENGTH: int = _C["ROOM_CODE_LENGTH"]
ROOM_CODE_ALPHABET: str = _C["ROOM_CODE_ALPHABET"]
MAX_PLAYERS: int = _C["MAX_PLAYERS"]
NICKNAME_MIN: int = _C["NICKNAME_MIN"]
NICKNAME_MAX: int = _C["NICKNAME_MAX"]
ROOM_IDLE_TTL_MS: int = _C["ROOM_IDLE_TTL_MS"]
OFFLINE_FORFEIT_MS: int = _C["OFFLINE_FORFEIT_MS"]
ACTION_RATE_LIMIT_PER_SEC: int = _C["ACTION_RATE_LIMIT_PER_SEC"]
RPS_PICK_TIMEOUT_MS: int = _C["RPS_PICK_TIMEOUT_MS"]
RPS_REVEAL_MS: int = _C["RPS_REVEAL_MS"]
GUESS_ROUND_MS: int = _C["GUESS_ROUND_MS"]
GUESS_HINT1_MS: int = _C["GUESS_HINT1_MS"]
GUESS_HINT2_MS: int = _C["GUESS_HINT2_MS"]
GUESS_REVEAL_MS: int = _C["GUESS_REVEAL_MS"]
GUESS_TEXT_MAX: int = _C["GUESS_TEXT_MAX"]
HANGMAN_SET_WORD_MS: int = _C["HANGMAN_SET_WORD_MS"]
HANGMAN_REVEAL_MS: int = _C["HANGMAN_REVEAL_MS"]
HANGMAN_MAX_WRONG: int = _C["HANGMAN_MAX_WRONG"]
HANGMAN_HINT_MAX: int = _C["HANGMAN_HINT_MAX"]
DOTS_TURN_MS: int = _C["DOTS_TURN_MS"]
DICE_TURN_MS: int = _C["DICE_TURN_MS"]
DICE_REVEAL_MS: int = _C["DICE_REVEAL_MS"]
NAMEIT_TURN_MS: int = _C["NAMEIT_TURN_MS"]
NAMEIT_CHALLENGE_WINDOW_MS: int = _C["NAMEIT_CHALLENGE_WINDOW_MS"]
NAMEIT_VOTE_MS: int = _C["NAMEIT_VOTE_MS"]
NAMEIT_TOPIC_MS: int = _C["NAMEIT_TOPIC_MS"]
NAMEIT_TOPIC_SUGGESTIONS: int = _C["NAMEIT_TOPIC_SUGGESTIONS"]
SESSION_POINTS_MAX: int = _C["SESSION_POINTS_MAX"]
HANGMAN_POT: int = _C["HANGMAN_POT"]
HANGMAN_WRONG_COST: int = _C["HANGMAN_WRONG_COST"]
HANGMAN_WORD_MIN: int = _C["HANGMAN_WORD_MIN"]
HANGMAN_WORD_MAX: int = _C["HANGMAN_WORD_MAX"]
HANGMAN_FLAG_WINDOW_MS: int = _C["HANGMAN_FLAG_WINDOW_MS"]
HANGMAN_VOTE_MS: int = _C["HANGMAN_VOTE_MS"]
GUESS_RANK_POINTS_FIRST: int = _C["GUESS_RANK_POINTS_FIRST"]
GUESS_RANK_POINTS_STEP: int = _C["GUESS_RANK_POINTS_STEP"]
GUESS_RANK_POINTS_FLOOR: int = _C["GUESS_RANK_POINTS_FLOOR"]
HOST_TRANSFER_MS: int = _C["HOST_TRANSFER_MS"]
ROOM_CLEANUP_INTERVAL_MS: int = _C["ROOM_CLEANUP_INTERVAL_MS"]
ROOM_CODE_MAX_ATTEMPTS: int = _C["ROOM_CODE_MAX_ATTEMPTS"]
NICKNAME_ALLOWED_PATTERN: str = _C["NICKNAME_ALLOWED_PATTERN"]
AVATAR_API_VERSION: str = _C["AVATAR_API_VERSION"]
AVATAR_STYLES: tuple[str, ...] = tuple(_C["AVATAR_STYLES"])
AVATAR_SEED_PATTERN: str = _C["AVATAR_SEED_PATTERN"]
USERNAME_PATTERN: str = _C["USERNAME_PATTERN"]
PASSWORD_MIN_LENGTH: int = _C["PASSWORD_MIN_LENGTH"]
AUTH_TOKEN_DAYS: int = _C["AUTH_TOKEN_DAYS"]
AUTH_RATE_LIMIT_PER_MIN: int = _C["AUTH_RATE_LIMIT_PER_MIN"]
STATS_MAX_IMPORT_GAMES: int = _C["STATS_MAX_IMPORT_GAMES"]
ACTIVITY_RETENTION_DAYS: int = _C["ACTIVITY_RETENTION_DAYS"]
DASHBOARD_MIN_GAMES_FOR_RATES: int = _C["DASHBOARD_MIN_GAMES_FOR_RATES"]
DASHBOARD_PAGE_SIZE: int = _C["DASHBOARD_PAGE_SIZE"]
GUEST_KEY_LENGTH: int = _C["GUEST_KEY_LENGTH"]
ADMIN_LOGIN_MAX_FAILS: int = _C["ADMIN_LOGIN_MAX_FAILS"]
ADMIN_LOGIN_LOCK_MINUTES: int = _C["ADMIN_LOGIN_LOCK_MINUTES"]
PLAYER_COLORS: tuple[str, ...] = tuple(_C["PLAYER_COLORS"])
