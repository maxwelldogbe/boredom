"""The contract a two-player game implements so games/series.py can run it.

An engine plays ONE game between two seats; the series wraps it in best-of matches and a
knockout bracket. Engines are pure like game modules (games/base.py): time arrives as `now`,
randomness comes only from the `rng` given to `init` (keep it in the state), and the state
they receive is already a private copy they may mutate.

Timeouts belong to the series: when `next_deadline` passes while `awaiting` is non-empty,
the series asks `random_action` for each owed move and feeds it to `apply`. `tick` only runs
the engine's other timers (and arms the first deadline: no clock runs before it).
"""

import random
from abc import ABC, abstractmethod
from typing import Any, Literal

from games.base import GameEvent

Status = Literal["ongoing", "winner", "draw"]
Outcome = tuple[Status, str | None]  # ("winner", player_id); otherwise the id is None


class MatchEngine(ABC):
    """One game between seat 1 (`player_a`) and seat 2 (`player_b`)."""

    @abstractmethod
    def init(
        self,
        player_a: str,
        player_b: str,
        settings: dict[str, Any],
        rng: random.Random,
        first_mover: str,
    ) -> Any:
        """A fresh game with `first_mover` to act first. No deadline until the first `tick`."""

    @abstractmethod
    def apply(
        self, state: Any, player_id: str, action: dict[str, Any], now: float
    ) -> tuple[Any, list[GameEvent]]:
        """One action. Raise GameError if not allowed. The same player may stay to move."""

    @abstractmethod
    def tick(self, state: Any, now: float) -> tuple[Any, list[GameEvent]]:
        """Arm the deadline if none is set and run non-move timers due at or before `now`."""

    @abstractmethod
    def awaiting(self, state: Any) -> list[str]:
        """Players who owe an action now (empty once the game is decided)."""

    @abstractmethod
    def random_action(self, state: Any, player_id: str, rng: random.Random) -> dict[str, Any]:
        """A random legal action for `player_id`, used when their time runs out."""

    @abstractmethod
    def public_view(self, state: Any) -> dict[str, Any]:
        """What anyone, spectators included, may see. Never hidden information."""

    @abstractmethod
    def view_for(self, state: Any, player_id: str) -> dict[str, Any]:
        """A seated player's view: the public view plus their own data (legal moves, ...)."""

    @abstractmethod
    def status(self, state: Any) -> Outcome:
        """("ongoing", None), ("winner", player_id) or ("draw", None)."""

    @abstractmethod
    def next_deadline(self, state: Any) -> float | None:
        """Earliest epoch-ms time something is due, or None."""
