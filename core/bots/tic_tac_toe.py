"""Tic-tac-toe bot. easy: random; medium: win, block, center, corner; hard: full minimax, except
that on its second move it slips with probability BOT_TTT_HARD_SLIP (a weaker move that still
blocks any immediate threat), so about one game in eight can be won."""

import random
from functools import cache
from typing import Any

from games.constants import BOT_TTT_HARD_SLIP
from games.tic_tac_toe import LINES

HARD_SLIP = BOT_TTT_HARD_SLIP  # module-level so tests can switch the slip off

CENTER = 4
CORNERS = (0, 2, 6, 8)


def choose(view: dict[str, Any], rng: random.Random, difficulty: str, budget_ms: float) -> dict:
    """A legal {"type": "place", "cell"} for the seat whose turn it is in `view`."""
    board: list[str | None] = list(view["board"])
    me = view["marks"][view["turn"]]
    legal: list[int] = list(view["legalMoves"])
    if difficulty == "easy":
        cell = rng.choice(legal)
    elif difficulty == "medium":
        cell = _medium(board, me, legal, rng)
    else:
        cell = _hard(board, me, legal, rng)
    return {"type": "place", "cell": cell}


def _other(mark: str) -> str:
    return "O" if mark == "X" else "X"


def _completing(board: list[str | None], mark: str, legal: list[int]) -> int | None:
    """A cell that completes a line for `mark`, or None."""
    for cell in legal:
        board[cell] = mark
        won = any(all(board[i] == mark for i in line) for line in LINES)
        board[cell] = None
        if won:
            return cell
    return None


def _medium(board: list[str | None], me: str, legal: list[int], rng: random.Random) -> int:
    for mark in (me, _other(me)):
        cell = _completing(board, mark, legal)
        if cell is not None:
            return cell
    if CENTER in legal:
        return CENTER
    corners = [c for c in CORNERS if c in legal]
    return rng.choice(corners or legal)


def _hard(board: list[str | None], me: str, legal: list[int], rng: random.Random) -> int:
    win = _completing(board, me, legal)
    if win is not None:
        return win
    scores = {}
    for cell in legal:
        board[cell] = me
        scores[cell] = -_negamax(tuple(board), _other(me))
        board[cell] = None
    best = max(scores.values())
    if sum(v == me for v in board) == 1 and rng.random() < HARD_SLIP:
        slips = [c for c in legal if scores[c] < best and not _gives_win(board, me, c)]
        if slips:
            return rng.choice(slips)
    return rng.choice([c for c in legal if scores[c] == best])


def _gives_win(board: list[str | None], me: str, cell: int) -> bool:
    """Whether playing `cell` leaves the opponent a line to complete at once."""
    board[cell] = me
    rest = [i for i, v in enumerate(board) if v is None]
    found = _completing(board, _other(me), rest) is not None
    board[cell] = None
    return found


@cache
def _negamax(board: tuple[str | None, ...], to_move: str) -> int:
    """Score for `to_move`: +1 win, 0 draw, -1 loss (both sides play perfectly)."""
    if any(board[a] is not None and board[a] == board[b] == board[c] for a, b, c in LINES):
        return -1  # the previous move completed a line
    empty = [i for i, v in enumerate(board) if v is None]
    if not empty:
        return 0
    cells = list(board)
    best = -2
    for cell in empty:
        cells[cell] = to_move
        best = max(best, -_negamax(tuple(cells), _other(to_move)))
        cells[cell] = None
        if best == 1:
            break
    return best
