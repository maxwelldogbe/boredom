"""Extension seam called after every finished game.

Future work (stats, stakes) plugs in here. For now it only logs.
"""

import logging

from games.base import GameResult

logger = logging.getLogger("rooms.hooks")


def on_game_finished(room_code: str, results: list[GameResult], game_id: str) -> None:
    """Called once per finished game with its final results."""
    logger.info("Game finished: room=%s game=%s results=%s", room_code, game_id, results)
