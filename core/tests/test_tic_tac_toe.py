"""Tic-tac-toe engine: win and draw detection, moves and views."""

import random

import pytest

from games import registry
from games.base import GameError
from games.constants import TTT_TURN_MS
from games.tic_tac_toe import LINES, TicTacToeEngine

ENGINE = TicTacToeEngine()
T0 = 1_000_000.0
DRAW = [0, 1, 2, 4, 3, 5, 7, 6, 8]  # alternating moves that fill the board with no line


def new(first="a"):
    state = ENGINE.init("a", "b", {}, random.Random(1), first)
    state, _ = ENGINE.tick(state, T0)
    return state


def play(state, cells, now=T0):
    for cell in cells:
        state, _ = ENGINE.apply(state, state.turn, {"type": "place", "cell": cell}, now)
    return state


def test_registered_with_settings() -> None:
    game = registry.get_game("tic_tac_toe")
    assert game is not None and game.validate_settings({}) == {"bestOf": 3}
    assert game.validate_settings({"bestOf": 1}) == {"bestOf": 1}
    for bad in [{"bestOf": 2}, {"bestOf": True}, {"x": 1}]:
        with pytest.raises(GameError):
            game.validate_settings(bad)


@pytest.mark.parametrize("line", LINES)
def test_every_line_wins(line) -> None:
    filler = [c for c in range(9) if c not in line]  # O only gets two marks: never a line
    moves = [line[0], filler[0], line[1], filler[1], line[2]]
    state = play(new(), moves)
    assert ENGINE.status(state) == ("winner", "a")
    view = ENGINE.public_view(state)
    assert view["winningCells"] == list(line) and view["lastMove"] == line[2]
    assert view["turn"] is None and view["turnDeadline"] is None and ENGINE.awaiting(state) == []


def test_full_board_is_a_draw() -> None:
    state = play(new(), DRAW)
    assert ENGINE.status(state) == ("draw", None)
    assert ENGINE.public_view(state)["winningCells"] is None


def test_turns_marks_and_errors() -> None:
    state = new(first="b")
    assert state.deadline == T0 + TTT_TURN_MS and ENGINE.awaiting(state) == ["b"]
    with pytest.raises(GameError) as exc:
        ENGINE.apply(state, "a", {"type": "place", "cell": 0}, T0)
    assert exc.value.code == "NOT_YOUR_TURN"
    state = play(state, [4], T0 + 5)
    assert state.deadline == T0 + 5 + TTT_TURN_MS
    for bad in [{"type": "place", "cell": 4}, {"type": "place", "cell": 9},
                {"type": "place", "cell": True}, {"type": "drop", "cell": 0}]:  # fmt: skip
        with pytest.raises(GameError):
            ENGINE.apply(state, "a", bad, T0)
    view = ENGINE.view_for(state, "a")
    assert view["board"][4] == "O" and view["marks"] == {"a": "X", "b": "O"}
    assert view["isYourTurn"] and 4 not in view["legalMoves"] and len(view["legalMoves"]) == 8
    assert ENGINE.view_for(state, "b")["legalMoves"] == []
