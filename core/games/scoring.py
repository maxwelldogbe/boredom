"""Session scoring: turns a game's placements into session points. Pure, no Django.

Games only report placements (and a raw display score); the room manager calls
`placement_points` so every game is worth the same on the session scoreboard.
"""

from collections import Counter

from games.base import GameResult


class ScoredResult(GameResult):
    """A game result plus the session points it earned (the room hook payload)."""

    points: float


def placement_points(placements: dict[str, int], max_points: float) -> dict[str, float]:
    """Points per player: max_points x (n - placement) / (n - 1), rounded to 2 decimals.

    `placements` uses competition ranking (1, 2, 2, 4): tied players share the AVERAGE of the
    positions they occupy. A lone player gets max_points.
    """
    n = len(placements)
    if n == 0:
        return {}
    if n == 1:
        return {pid: round(float(max_points), 2) for pid in placements}

    def worth(position: int) -> float:
        return max_points * (n - position) / (n - 1)

    sizes = Counter(placements.values())
    shared = {
        place: sum(worth(pos) for pos in range(place, place + size)) / size
        for place, size in sizes.items()
    }
    return {pid: round(shared[place], 2) for pid, place in placements.items()}


def score_results(results: list[GameResult], max_points: float) -> list[ScoredResult]:
    """Attach session points to each game result, keeping the game's order."""
    points = placement_points({r["player_id"]: r["placement"] for r in results}, max_points)
    return [{**r, "points": points[r["player_id"]]} for r in results]
