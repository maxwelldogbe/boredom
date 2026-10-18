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
DICE_TURN_MS: int = _C["DICE_TURN_MS"]
NAMEIT_TURN_MS: int = _C["NAMEIT_TURN_MS"]
NAMEIT_CHALLENGE_WINDOW_MS: int = _C["NAMEIT_CHALLENGE_WINDOW_MS"]
NAMEIT_VOTE_MS: int = _C["NAMEIT_VOTE_MS"]
HOST_TRANSFER_MS: int = _C["HOST_TRANSFER_MS"]
ROOM_CLEANUP_INTERVAL_MS: int = _C["ROOM_CLEANUP_INTERVAL_MS"]
ROOM_CODE_MAX_ATTEMPTS: int = _C["ROOM_CODE_MAX_ATTEMPTS"]
NICKNAME_ALLOWED_PATTERN: str = _C["NICKNAME_ALLOWED_PATTERN"]
EMOJI_PRESETS: tuple[str, ...] = tuple(_C["EMOJI_PRESETS"])
PLAYER_COLORS: tuple[str, ...] = tuple(_C["PLAYER_COLORS"])
