"""Bot move choosers for solo games: pure functions, one module per game.

`choose(view, rng, difficulty, budget_ms) -> action` reads only the seat view a human in the
bot's seat would get (plus `serverNow`) and always returns a legal action. A real-time game's
chooser returns `(action, delay_ms)` instead: the driver sends it that many ms from serverNow.
The time budget is checked inside the search, which then returns the best move found so far.
"""

from collections.abc import Callable
from typing import Any

from bots import connect_four, dots_and_boxes, penalty_kick, tic_tac_toe

Chooser = Callable[..., dict[str, Any]]

CHOOSERS: dict[str, Chooser] = {
    "tic_tac_toe": tic_tac_toe.choose,
    "connect_four": connect_four.choose,
    "dots_and_boxes": dots_and_boxes.choose,
    "penalty_kick": penalty_kick.choose,
}
