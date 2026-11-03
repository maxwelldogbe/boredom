"""Tic-tac-toe: a 3x3 MatchEngine run as best-of matches in a bracket by games/series.py.

Seat 1 is X, seat 2 is O; whoever is the game's first mover opens. Three in a row (across,
down or diagonal) wins; a full board without one is a draw. Each turn lasts TTT_TURN_MS.
"""

import random
from dataclasses import dataclass, field
from typing import Any

from games.base import GameError, GameEvent
from games.constants import TTT_TURN_MS
from games.match_engine import MatchEngine, Outcome
from games.series import SeriesGame

LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # columns
    (0, 4, 8), (2, 4, 6),  # diagonals
)  # fmt: skip


@dataclass
class TttState:
    a: str  # X
    b: str  # O
    first: str
    turn: str
    board: list[str | None] = field(default_factory=lambda: [None] * 9)  # player id per cell
    deadline: float | None = None
    last_move: int | None = None
    winner: str | None = None
    winning_cells: list[int] | None = None


def winning_line(board: list[str | None]) -> tuple[str, list[int]] | None:
    """The owner and cells of a completed line, or None."""
    for line in LINES:
        owner = board[line[0]]
        if owner is not None and all(board[i] == owner for i in line):
            return owner, list(line)
    return None


class TicTacToeEngine(MatchEngine):
    def init(self, player_a, player_b, settings, rng, first_mover) -> TttState:
        return TttState(player_a, player_b, first_mover, first_mover)

    def apply(self, state: TttState, player_id, action, now) -> tuple[Any, list[GameEvent]]:
        if action.get("type") != "place":
            raise GameError("INVALID_ACTION", "Unknown action.")
        if self.status(state)[0] != "ongoing":
            raise GameError("INVALID_ACTION", "The game is over.")
        if player_id != state.turn:
            raise GameError("NOT_YOUR_TURN", "Wait for your turn.")
        cell = action.get("cell")
        if type(cell) is not int or not 0 <= cell <= 8 or state.board[cell] is not None:
            raise GameError("INVALID_ACTION", "Pick an empty cell.")
        state.board[cell], state.last_move = player_id, cell
        found = winning_line(state.board)
        if found is not None:
            state.winner, state.winning_cells = found
        state.turn = state.b if player_id == state.a else state.a
        ongoing = self.status(state)[0] == "ongoing"
        state.deadline = now + TTT_TURN_MS if ongoing else None
        return state, []

    def tick(self, state: TttState, now) -> tuple[Any, list[GameEvent]]:
        if state.deadline is None and self.status(state)[0] == "ongoing":
            state.deadline = now + TTT_TURN_MS
        return state, []

    def awaiting(self, state: TttState) -> list[str]:
        return [state.turn] if self.status(state)[0] == "ongoing" else []

    def random_action(self, state: TttState, player_id, rng: random.Random) -> dict[str, Any]:
        return {"type": "place", "cell": rng.choice(self._empty(state))}

    def public_view(self, state: TttState) -> dict[str, Any]:
        marks = {state.a: "X", state.b: "O"}
        ongoing = self.status(state)[0] == "ongoing"
        return {
            "board": [marks[p] if p is not None else None for p in state.board],
            "marks": marks,
            "firstMover": state.first,
            "turn": state.turn if ongoing else None,
            "turnDeadline": state.deadline,
            "lastMove": state.last_move,
            "winner": state.winner,
            "winningCells": state.winning_cells,
        }

    def view_for(self, state: TttState, player_id) -> dict[str, Any]:
        view = self.public_view(state)
        mine = view["turn"] == player_id
        return {**view, "isYourTurn": mine, "legalMoves": self._empty(state) if mine else []}

    def status(self, state: TttState) -> Outcome:
        if state.winner is not None:
            return "winner", state.winner
        if all(c is not None for c in state.board):
            return "draw", None
        return "ongoing", None

    def next_deadline(self, state: TttState) -> float | None:
        return state.deadline

    @staticmethod
    def _empty(state: TttState) -> list[int]:
        return [i for i, owner in enumerate(state.board) if owner is None]


class TicTacToe(SeriesGame):
    id = "tic_tac_toe"
    name = "Tic-Tac-Toe"
    default_settings: dict[str, Any] = {"bestOf": 3}
    engine = TicTacToeEngine()
