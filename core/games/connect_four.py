"""Connect Four: a 7x6 gravity board as a MatchEngine, run in matches and a bracket by
games/series.py.

Rows run top (0) to bottom (5); a disc dropped in a column lands in its lowest empty row.
Four in a row across, down or diagonally wins; a full board without one is a draw. Each
turn lasts C4_TURN_MS.
"""

import random
from dataclasses import dataclass, field
from typing import Any

from games.base import GameError, GameEvent
from games.constants import C4_TURN_MS
from games.match_engine import MatchEngine, Outcome
from games.series import SeriesGame

COLUMNS = 7
ROWS = 6
DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))  # across, down, both diagonals


@dataclass
class C4State:
    a: str  # seat 1
    b: str  # seat 2
    first: str
    turn: str
    board: list[list[str | None]] = field(
        default_factory=lambda: [[None] * COLUMNS for _ in range(ROWS)]
    )  # [row][column] -> player id
    deadline: float | None = None
    last_move: dict[str, Any] | None = None
    winner: str | None = None
    winning_cells: list[list[int]] | None = None


def winning_run(board: list[list[str | None]], row: int, col: int) -> list[list[int]] | None:
    """Cells of a run of 4+ through (row, col) for its owner, or None."""
    owner = board[row][col]
    for dr, dc in DIRECTIONS:
        run = [[row, col]]
        for sign in (1, -1):
            r, c = row + sign * dr, col + sign * dc
            while 0 <= r < ROWS and 0 <= c < COLUMNS and board[r][c] == owner:
                run.append([r, c])
                r, c = r + sign * dr, c + sign * dc
        if len(run) >= 4:
            return sorted(run)
    return None


class ConnectFourEngine(MatchEngine):
    def init(self, player_a, player_b, settings, rng, first_mover) -> C4State:
        return C4State(player_a, player_b, first_mover, first_mover)

    def apply(self, state: C4State, player_id, action, now) -> tuple[Any, list[GameEvent]]:
        if action.get("type") != "drop":
            raise GameError("INVALID_ACTION", "Unknown action.")
        if self.status(state)[0] != "ongoing":
            raise GameError("INVALID_ACTION", "The game is over.")
        if player_id != state.turn:
            raise GameError("NOT_YOUR_TURN", "Wait for your turn.")
        col = action.get("column")
        if type(col) is not int or col not in self._open_columns(state):
            raise GameError("INVALID_ACTION", "Pick a column that is not full.")
        row = max(r for r in range(ROWS) if state.board[r][col] is None)
        state.board[row][col] = player_id
        state.last_move = {"row": row, "column": col, "playerId": player_id}
        run = winning_run(state.board, row, col)
        if run is not None:
            state.winner, state.winning_cells = player_id, run
        state.turn = state.b if player_id == state.a else state.a
        ongoing = self.status(state)[0] == "ongoing"
        state.deadline = now + C4_TURN_MS if ongoing else None
        return state, []

    def tick(self, state: C4State, now) -> tuple[Any, list[GameEvent]]:
        if state.deadline is None and self.status(state)[0] == "ongoing":
            state.deadline = now + C4_TURN_MS
        return state, []

    def awaiting(self, state: C4State) -> list[str]:
        return [state.turn] if self.status(state)[0] == "ongoing" else []

    def random_action(self, state: C4State, player_id, rng: random.Random) -> dict[str, Any]:
        return {"type": "drop", "column": rng.choice(self._open_columns(state))}

    def public_view(self, state: C4State) -> dict[str, Any]:
        seats = {state.a: 1, state.b: 2}
        ongoing = self.status(state)[0] == "ongoing"
        return {
            "board": [[seats[p] if p is not None else None for p in row] for row in state.board],
            "seats": seats,
            "firstMover": state.first,
            "turn": state.turn if ongoing else None,
            "turnDeadline": state.deadline,
            "lastMove": state.last_move,
            "winner": state.winner,
            "winningCells": state.winning_cells,
        }

    def view_for(self, state: C4State, player_id) -> dict[str, Any]:
        view = self.public_view(state)
        mine = view["turn"] == player_id
        return {**view, "isYourTurn": mine, "legalMoves": self._open_columns(state) if mine else []}

    def status(self, state: C4State) -> Outcome:
        if state.winner is not None:
            return "winner", state.winner
        if not self._open_columns(state):
            return "draw", None
        return "ongoing", None

    def next_deadline(self, state: C4State) -> float | None:
        return state.deadline

    @staticmethod
    def _open_columns(state: C4State) -> list[int]:
        return [c for c in range(COLUMNS) if state.board[0][c] is None]


class ConnectFour(SeriesGame):
    id = "connect_four"
    name = "Connect Four"
    default_settings: dict[str, Any] = {"bestOf": 3}
    engine = ConnectFourEngine()
