"""Dots and Boxes (plan section 10): draw lines in turn, close boxes to claim them.

Lines are `h:r:c` (r 0..size, c 0..size-1) and `v:r:c` (r 0..size-1, c 0..size).
Turn order is shuffled at the start. Closing a box scores it and keeps the turn.
The game ends when every box is claimed.
On turn timeout the server draws a random line that gives away no third side when one
exists. A forfeiting player leaves the turn order; their lines and boxes stay on the board.
"""

import random
import re
from dataclasses import dataclass, field
from typing import Any

from games.base import (
    ForfeitReason,
    GameError,
    GameEvent,
    GameModule,
    GameResult,
    competition_placements,
)
from games.constants import DOTS_TURN_MS

SIZES = range(4, 8)
LINE_RE = re.compile(r"^([hv]):(\d+):(\d+)$")

Box = tuple[int, int]


@dataclass
class DotsState:
    size: int
    order: list[str]
    rng: random.Random
    lines: dict[str, int] = field(default_factory=dict)  # line id -> drawer index
    boxes: list[list[int | None]] = field(default_factory=list)  # owner index per box
    turn_index: int = 0
    phase: str = "playing"  # playing | done
    turn_deadline: float | None = None
    last_move: dict[str, Any] | None = None
    out: list[str] = field(default_factory=list)  # forfeited: skipped in the turn order

    @property
    def current(self) -> str:
        return self.order[self.turn_index]

    def next_turn_index(self) -> int:
        """The next player after the current one who is still in the game (wrapping)."""
        for step in range(1, len(self.order) + 1):
            index = (self.turn_index + step) % len(self.order)
            if self.order[index] not in self.out:
                return index
        return self.turn_index


def all_lines(size: int) -> list[str]:
    """Every line id on a board of `size` x `size` boxes."""
    horizontal = [f"h:{r}:{c}" for r in range(size + 1) for c in range(size)]
    vertical = [f"v:{r}:{c}" for r in range(size) for c in range(size + 1)]
    return horizontal + vertical


def box_sides(r: int, c: int) -> tuple[str, str, str, str]:
    """The four line ids around box (r, c)."""
    return (f"h:{r}:{c}", f"h:{r + 1}:{c}", f"v:{r}:{c}", f"v:{r}:{c + 1}")


def adjacent_boxes(line_id: str, size: int) -> list[Box]:
    """The one or two boxes that `line_id` borders."""
    kind, r, c = parse_line(line_id, size)
    candidates = [(r - 1, c), (r, c)] if kind == "h" else [(r, c - 1), (r, c)]
    return [(br, bc) for br, bc in candidates if 0 <= br < size and 0 <= bc < size]


def parse_line(line_id: Any, size: int) -> tuple[str, int, int]:
    """Split a line id and check it is on the board, or raise GameError(INVALID_ACTION)."""
    match = LINE_RE.fullmatch(line_id) if isinstance(line_id, str) else None
    if match is None:
        raise GameError("INVALID_ACTION", "Unknown line.")
    kind, r, c = match.group(1), int(match.group(2)), int(match.group(3))
    rows, cols = (size + 1, size) if kind == "h" else (size, size + 1)
    if not (0 <= r < rows and 0 <= c < cols):
        raise GameError("INVALID_ACTION", "Unknown line.")
    return kind, r, c


def compute_scores(state: DotsState) -> dict[str, int]:
    """Boxes owned by each player. The only place Dots and Boxes scoring lives."""
    scores = dict.fromkeys(state.order, 0)
    for row in state.boxes:
        for owner in row:
            if owner is not None:
                scores[state.order[owner]] += 1
    return scores


class DotsAndBoxes(GameModule):
    id = "dots_and_boxes"
    name = "Dots and Boxes"
    min_players = 2
    max_players = 4
    default_settings: dict[str, Any] = {"size": 5}

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = {**self.default_settings, **settings}
        if set(merged) != set(self.default_settings):
            raise GameError("INVALID_ACTION", "Unknown setting.")
        size = merged["size"]
        if not isinstance(size, int) or isinstance(size, bool) or size not in SIZES:
            raise GameError("INVALID_ACTION", "size must be 4 to 7.")
        return merged

    def init(self, players: list[str], settings: dict[str, Any], rng: random.Random, now: float):
        size = settings["size"]
        order = list(players)
        rng.shuffle(order)  # random turn order: nobody gets the first move by seating
        return DotsState(
            size=size,
            order=order,
            rng=rng,
            boxes=[[None] * size for _ in range(size)],
            turn_deadline=now + DOTS_TURN_MS,
        )

    # ----- actions -------------------------------------------------------------------------

    def handle_action(self, state: DotsState, player_id, action, now) -> tuple[Any, list]:
        if action.get("type") != "drawLine":
            raise GameError("INVALID_ACTION", "Unknown action.")
        if state.phase != "playing":
            raise GameError("INVALID_ACTION", "The game is over.")
        if player_id not in state.order or player_id in state.out:
            raise GameError("INVALID_ACTION", "You are not in this game.")
        if player_id != state.current:
            raise GameError("NOT_YOUR_TURN", "Wait for your turn.")
        line_id = action.get("id")
        parse_line(line_id, state.size)
        if line_id in state.lines:
            raise GameError("INVALID_ACTION", "That line is already drawn.")
        self._draw(state, line_id, now, auto=None)
        return state, []

    def _draw(self, state: DotsState, line_id: str, now: float, auto: str | None) -> None:
        """Draw for the current player, claim closed boxes, then pass or keep the turn."""
        drawer = state.turn_index
        state.lines[line_id] = drawer
        claimed = []
        for r, c in adjacent_boxes(line_id, state.size):
            if all(side in state.lines for side in box_sides(r, c)):
                state.boxes[r][c] = drawer
                claimed.append([r, c])
        state.last_move = {
            "lineId": line_id,
            "playerId": state.order[drawer],
            "boxes": claimed,
            "auto": auto,
        }
        if all(owner is not None for row in state.boxes for owner in row):
            state.phase, state.turn_deadline = "done", None
            return
        if not claimed:
            state.turn_index = state.next_turn_index()
        state.turn_deadline = now + DOTS_TURN_MS

    def _auto_line(self, state: DotsState) -> str:
        """A random free line that leaves no box with three sides, else any free line."""
        free = [line for line in all_lines(state.size) if line not in state.lines]
        safe = [line for line in free if not self._gives_third_side(state, line)]
        return state.rng.choice(safe or free)

    def _gives_third_side(self, state: DotsState, line_id: str) -> bool:
        for r, c in adjacent_boxes(line_id, state.size):
            drawn = sum(side in state.lines for side in box_sides(r, c))
            if drawn == 2:
                return True
        return False

    # ----- timers and forfeits ----------------------------------------------------------------

    def tick(self, state: DotsState, now) -> tuple[Any, list[GameEvent]]:
        while self.next_deadline(state) is not None and now >= (state.turn_deadline or 0):
            self._draw(state, self._auto_line(state), now, auto="timeout")
        return state, []

    def forfeit(
        self, state: DotsState, player_id: str, now: float, reason: ForfeitReason
    ) -> tuple[Any, list[GameEvent]]:
        if state.phase != "playing" or player_id not in state.order or player_id in state.out:
            return state, []
        state.out.append(player_id)
        if state.current == player_id:
            state.turn_index = state.next_turn_index()
            state.turn_deadline = now + DOTS_TURN_MS
        return state, []

    def next_deadline(self, state: DotsState) -> float | None:
        return state.turn_deadline if state.phase == "playing" else None

    # ----- views and results -------------------------------------------------------------------

    def get_view(self, state: DotsState, player_id: str) -> dict[str, Any]:
        playing = state.phase == "playing"
        return {
            "phase": state.phase,
            "size": state.size,
            "order": list(state.order),
            "currentPlayerId": state.current if playing else None,
            "isYourTurn": playing and player_id == state.current,
            "lines": {line: state.order[i] for line, i in state.lines.items()},
            "boxes": [[None if o is None else state.order[o] for o in row] for row in state.boxes],
            "scores": compute_scores(state),
            "lastMove": dict(state.last_move) if state.last_move else None,
            "turnDeadline": state.turn_deadline,
        }

    def is_over(self, state: DotsState) -> bool:
        return state.phase == "done"

    def get_results(self, state: DotsState) -> list[GameResult]:
        scores = compute_scores(state)
        placements = competition_placements({p: float(s) for p, s in scores.items()})
        ranked = sorted(scores, key=lambda p: placements[p])
        return [{"player_id": p, "placement": placements[p], "score": scores[p]} for p in ranked]
