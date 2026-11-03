"""Penalty kick bot. Returns (action, delay_ms): it acts at a chosen moment, not after a think.

It reads only its seat's view. Shooting never looks at the keeper (no information about the
human's dive exists in the aiming view anyway). Keeping uses what a human keeper sees at
launch: the ball's real aim (flight.ball.to) and launchAt; the dive lands after a sampled
reaction time, so a slow reaction is simply too late.
"""

import random
from typing import Any

from games.constants import BOT_PENALTY_SHOOT_MS_MAX, BOT_PENALTY_SHOOT_MS_MIN
from games.penalty_kick import AIM_RANGE, DIVE_RANGE

SHOT = {  # aim sd, power range
    "easy": (0.25, (0.3, 0.95)),
    "medium": (0.1, (0.5, 0.85)),
    "hard": (0.05, (0.6, 0.8)),
}
MEDIUM_CORNERS = ((0.15, 0.25), (0.15, 0.75), (0.85, 0.25), (0.85, 0.75))
HARD_X = (0.12, 0.88)
HARD_Y = (0.2, 0.8)
KEEP = {  # dive sd, reaction ms after launch
    "easy": (0.30, (800, 1100)),
    "medium": (0.16, (600, 850)),
    "hard": (0.09, (450, 650)),
}
EASY_GUESS = 0.25  # easy dives to a random point this often


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return min(bounds[1], max(bounds[0], value))


def choose(
    view: dict[str, Any], rng: random.Random, difficulty: str, budget_ms: float
) -> tuple[dict[str, Any], float]:
    """The bot's action and how many ms from `view["serverNow"]` to send it."""
    if view.get("phase") == "flight" and view.get("yourRole") == "keeper":
        return _keep(view, rng, difficulty)
    return _shoot(rng, difficulty)


def _shoot(rng: random.Random, difficulty: str) -> tuple[dict[str, Any], float]:
    sd, (low, high) = SHOT.get(difficulty, SHOT["medium"])
    if difficulty == "easy":
        cx, cy = 0.5, 0.5
    elif difficulty == "hard":
        cx, cy = rng.choice(HARD_X), rng.uniform(*HARD_Y)
    else:
        cx, cy = rng.choice(MEDIUM_CORNERS)
    aim = {"x": _clamp(rng.gauss(cx, sd), AIM_RANGE), "y": _clamp(rng.gauss(cy, sd), AIM_RANGE)}
    power = rng.uniform(low, high)
    delay = rng.uniform(BOT_PENALTY_SHOOT_MS_MIN, BOT_PENALTY_SHOOT_MS_MAX)
    return {"type": "shoot", "aim": aim, "power": power}, delay


def _keep(
    view: dict[str, Any], rng: random.Random, difficulty: str
) -> tuple[dict[str, Any], float]:
    flight = view["flight"]
    sd, (low, high) = KEEP.get(difficulty, KEEP["medium"])
    to = flight["ball"]["to"]
    if difficulty == "easy" and rng.random() < EASY_GUESS:
        x, y = rng.uniform(*DIVE_RANGE), rng.uniform(0.0, 1.0)
    else:
        x, y = rng.gauss(to["x"], sd), rng.gauss(to["y"], sd)
    dive = {"type": "dive", "x": _clamp(x, DIVE_RANGE), "y": _clamp(y, DIVE_RANGE)}
    at = flight["launchAt"] + rng.uniform(low, high)
    return dive, max(0.0, at - view.get("serverNow", flight["launchAt"]))
