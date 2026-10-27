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


def rank_with_forfeits(
    results: list[GameResult], forfeited_at: dict[str, float], players: list[str]
) -> list[GameResult]:
    """Re-place a game's results so every forfeiter ranks below every player who stayed.

    Stayers keep the game's relative order (ties stay tied). Forfeiters follow, the one who
    left later ranking higher; forfeits at the same time share a placement. Every id in
    `players` gets a row (score 0 if the game reported none).
    """
    by_id = {r["player_id"]: r for r in results}
    rows = [by_id.get(p, {"player_id": p, "placement": len(players), "score": 0}) for p in players]
    stayers = [r for r in rows if r["player_id"] not in forfeited_at]
    gone = [r for r in rows if r["player_id"] in forfeited_at]
    placed: list[GameResult] = []
    for r in stayers:
        better = sum(1 for o in stayers if o["placement"] < r["placement"])
        placed.append({**r, "placement": 1 + better})
    for r in gone:
        at = forfeited_at[r["player_id"]]
        later = sum(1 for o in gone if forfeited_at[o["player_id"]] > at)
        placed.append({**r, "placement": len(stayers) + 1 + later})
    return sorted(placed, key=lambda r: r["placement"])


def score_results(results: list[GameResult], max_points: float) -> list[ScoredResult]:
    """Attach session points to each game result, keeping the game's order."""
    points = placement_points({r["player_id"]: r["placement"] for r in results}, max_points)
    return [{**r, "points": points[r["player_id"]]} for r in results]
