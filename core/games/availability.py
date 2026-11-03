"""Games staff turned off from the admin dashboard (analytics.GameAvailability).

The server is one process, so the off set is kept here in memory: loaded from the database
before the first room needs it, and replaced whenever staff change it. Off games cannot be
selected or started, and clients hide them (RoomPublic.disabledGames).
"""

import logging

from channels.db import database_sync_to_async

logger = logging.getLogger("games.availability")

_disabled: frozenset[str] | None = None  # None until loaded


def disabled() -> frozenset[str]:
    """Game ids that are turned off (empty until loaded)."""
    return _disabled or frozenset()


def is_enabled(game_id: str) -> bool:
    return game_id not in disabled()


def load() -> frozenset[str]:
    """Read the off set from the database."""
    from analytics.models import GameAvailability

    global _disabled
    rows = GameAvailability.objects.filter(enabled=False).values_list("game_id", flat=True)
    _disabled = frozenset(rows)
    return _disabled


async def ensure_loaded() -> None:
    """Load once; on a database error every game stays on and the next call retries."""
    if _disabled is not None:
        return
    try:
        await database_sync_to_async(load)()
    except Exception:
        logger.warning("Could not load game availability; all games are on", exc_info=True)


def set_enabled(game_id: str, enabled: bool, user=None) -> frozenset[str]:
    """Save one game's switch and return the new off set."""
    from analytics.models import GameAvailability

    GameAvailability.objects.update_or_create(
        game_id=game_id, defaults={"enabled": enabled, "changed_by": user}
    )
    return load()


def reset(off: frozenset[str] | None = None) -> None:
    """Replace the in-memory set (tests)."""
    global _disabled
    _disabled = off
