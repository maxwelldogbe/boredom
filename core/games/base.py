"""The contract every game module implements.

Modules are pure: no Django, sockets, asyncio, wall clocks or global randomness.
- Time arrives as `now`: epoch milliseconds (float), supplied by the room manager.
- Randomness comes only from the `rng` passed to `init`; modules keep it in their state.
- The room manager deep-copies state before `handle_action`/`tick`, so a module may
  mutate the state it receives. On GameError the manager discards the copy, so a
  failed action never changes anything.
"""

import random
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal, TypedDict

ForfeitReason = Literal["quit", "left", "offline"]


class GameError(Exception):
    """An invalid action. `code` is a protocol error code such as INVALID_ACTION."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class GameEvent(TypedDict):
    """A transient moment pushed to clients as `game:event` (reveal, round over, ...)."""

    kind: str
    data: dict[str, Any]


class GameResult(TypedDict):
    """One player's final outcome. Placement 1 is best; tied players share a placement.

    `score` is the raw in-game score, for display only. Session points are not a game's
    business: the room manager derives them from placements (games/scoring.py).
    """

    player_id: str
    placement: int
    score: float


class GameModule(ABC):
    """Abstract game module. Subclasses set the class attributes and implement every method."""

    id: ClassVar[str]
    name: ClassVar[str]
    min_players: ClassVar[int]
    max_players: ClassVar[int]
    default_settings: ClassVar[dict[str, Any]]

    @abstractmethod
    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Return complete settings (defaults merged in), or raise GameError(INVALID_ACTION)."""

    @abstractmethod
    def init(
        self, players: list[str], settings: dict[str, Any], rng: random.Random, now: float
    ) -> Any:
        """Create the initial state. `players` are player ids in seat (join) order.

        Raise GameError(INVALID_ACTION) if the game cannot start with these players/settings.
        """

    @abstractmethod
    def handle_action(
        self, state: Any, player_id: str, action: dict[str, Any], now: float
    ) -> tuple[Any, list[GameEvent]]:
        """Apply one player action. Raise GameError if it is not allowed."""

    @abstractmethod
    def tick(self, state: Any, now: float) -> tuple[Any, list[GameEvent]]:
        """Advance timers: timeouts, auto-moves, phase changes due at or before `now`."""

    def on_presence(
        self, state: Any, player_id: str, online: bool, now: float
    ) -> tuple[Any, list[GameEvent]]:
        """A player went offline or came back. Default: ignore. Override for offline rules."""
        return state, []

    def forfeit(
        self, state: Any, player_id: str, now: float, reason: ForfeitReason
    ) -> tuple[Any, list[GameEvent]]:
        """Remove `player_id` from the running game for good: the only way a player leaves one.

        The room manager calls it for game:quit, room:leave and the offline timeout, once per
        player. The module drops the player from play under its own rules; the game is over
        once exactly one active player remains (`is_over`). Placements of forfeiters are
        decided by the room manager (games/scoring.py), not here.
        """
        raise NotImplementedError(f"{self.id} does not support forfeits yet.")

    @abstractmethod
    def get_view(self, state: Any, player_id: str) -> dict[str, Any]:
        """What `player_id` may see. Must never include secrets they are not entitled to."""

    @abstractmethod
    def next_deadline(self, state: Any) -> float | None:
        """Earliest epoch-ms time at which `tick` has work to do, or None."""

    @abstractmethod
    def is_over(self, state: Any) -> bool:
        """True once the game has finished."""

    @abstractmethod
    def get_results(self, state: Any) -> list[GameResult]:
        """Final placement and raw score for every player. Only valid once `is_over`."""


def competition_placements(values: dict[str, float]) -> dict[str, int]:
    """Rank players by value, higher is better; ties share a placement (1, 2, 2, 4)."""
    return {pid: 1 + sum(1 for v in values.values() if v > value) for pid, value in values.items()}
