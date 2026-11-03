"""Connect Four bot.

easy: win, else block, else a random open column. medium: alpha-beta to depth 4. hard:
alpha-beta up to depth 8. Both deepen iteratively within the time budget, order
moves center first and score positions with a center-weighted table; medium and hard also
take a win or block a threat before searching.
"""

import random
import time
from typing import Any

from games.connect_four import COLUMNS, ROWS

ORDER = (3, 2, 4, 1, 5, 0, 6)  # center first
WEIGHTS = (
    (3, 4, 5, 7, 5, 4, 3),
    (4, 6, 8, 10, 8, 6, 4),
    (5, 8, 11, 13, 11, 8, 5),
    (5, 8, 11, 13, 11, 8, 5),
    (4, 6, 8, 10, 8, 6, 4),
    (3, 4, 5, 7, 5, 4, 3),
)
WIN = 1_000_000
MEDIUM_DEPTH = 4
HARD_MAX_DEPTH = 8


class _Timeout(Exception):
    pass


class _Board:
    """Rows top (0) to bottom; cells hold 0 (empty), 1 or 2."""

    def __init__(self, rows: list[list[int | None]]) -> None:
        self.cells = [[v or 0 for v in row] for row in rows]
        self.free = [
            max((r for r in range(ROWS) if self.cells[r][c] == 0), default=-1)
            for c in range(COLUMNS)
        ]
        self.filled = sum(1 for row in self.cells for v in row if v)

    def open_columns(self) -> list[int]:
        return [c for c in ORDER if self.free[c] >= 0]

    def drop(self, col: int, seat: int) -> int:
        row = self.free[col]
        self.cells[row][col] = seat
        self.free[col] -= 1
        self.filled += 1
        return row

    def undo(self, col: int) -> None:
        self.free[col] += 1
        self.cells[self.free[col]][col] = 0
        self.filled -= 1

    def wins_at(self, row: int, col: int) -> bool:
        seat = self.cells[row][col]
        for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            count = 1
            for sign in (1, -1):
                r, c = row + sign * dr, col + sign * dc
                while 0 <= r < ROWS and 0 <= c < COLUMNS and self.cells[r][c] == seat:
                    count += 1
                    r, c = r + sign * dr, c + sign * dc
            if count >= 4:
                return True
        return False

    def winning_move(self, seat: int) -> int | None:
        """A column where `seat` wins at once, or None."""
        for col in self.open_columns():
            row = self.drop(col, seat)
            won = self.wins_at(row, col)
            self.undo(col)
            if won:
                return col
        return None

    def evaluate(self, seat: int) -> int:
        score = 0
        for r in range(ROWS):
            for c in range(COLUMNS):
                v = self.cells[r][c]
                if v:
                    score += WEIGHTS[r][c] if v == seat else -WEIGHTS[r][c]
        return score


def choose(view: dict[str, Any], rng: random.Random, difficulty: str, budget_ms: float) -> dict:
    """A legal {"type": "drop", "column"} for the seat whose turn it is in `view`."""
    deadline = time.perf_counter() + budget_ms / 1000
    board = _Board(view["board"])
    me = view["seats"][view["turn"]]
    legal = list(view["legalMoves"])
    col = board.winning_move(me)
    if col is None:
        col = board.winning_move(3 - me)
    if col is None:
        if difficulty == "easy":
            col = rng.choice(legal)
        else:
            depth = MEDIUM_DEPTH if difficulty == "medium" else HARD_MAX_DEPTH
            col = _deepen(board, me, depth, deadline, rng)
    if col not in legal:  # never happens; a legal move is the contract
        col = rng.choice(legal)
    return {"type": "drop", "column": col}


def _deepen(board: _Board, me: int, max_depth: int, deadline: float, rng: random.Random) -> int:
    """The best column of the deepest search finished before the deadline."""
    best = board.open_columns()[0]
    for depth in range(1, max_depth + 1):
        try:
            best = _root(board, me, depth, deadline, rng)
        except _Timeout:
            break
    return best


def _root(board: _Board, me: int, depth: int, deadline: float, rng: random.Random) -> int:
    scores: dict[int, int] = {}
    alpha = -WIN * 2
    for col in board.open_columns():
        row = board.drop(col, me)
        if board.wins_at(row, col):
            score = WIN + depth
        else:
            score = -_negamax(board, 3 - me, depth - 1, -WIN * 2, -alpha + 1, deadline)
        board.undo(col)
        scores[col] = score
        alpha = max(alpha, score)
    best = max(scores.values())
    return rng.choice([c for c, s in scores.items() if s == best])


def _negamax(board: _Board, seat: int, depth: int, alpha: int, beta: int, deadline: float) -> int:
    """Value for `seat` (to move). A win sooner scores higher."""
    if time.perf_counter() > deadline:
        raise _Timeout
    columns = board.open_columns()
    if not columns:
        return 0
    if depth == 0:
        return board.evaluate(seat)
    best = -WIN * 2
    for col in columns:
        row = board.drop(col, seat)
        if board.wins_at(row, col):
            value = WIN + depth
        else:
            value = -_negamax(board, 3 - seat, depth - 1, -beta, -alpha, deadline)
        board.undo(col)
        if value > best:
            best = value
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break
    return best
