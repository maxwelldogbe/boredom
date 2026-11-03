"""Connect Four engine: gravity, win and draw detection, moves and views."""

import random

import pytest

from games import registry
from games.base import GameError
from games.connect_four import ConnectFourEngine
from games.constants import C4_TURN_MS

ENGINE = ConnectFourEngine()
T0 = 1_000_000.0
DRAW = [3, 3, 0, 2, 5, 4, 5, 6, 4, 2, 2, 3, 3, 5, 5, 2, 2, 4, 3, 3, 1,
        1, 2, 1, 5, 5, 0, 4, 0, 4, 4, 6, 6, 6, 6, 0, 1, 0, 6, 0, 1, 1]  # fmt: skip


def new(first="a"):
    state = ENGINE.init("a", "b", {}, random.Random(1), first)
    state, _ = ENGINE.tick(state, T0)
    return state


def play(state, columns, now=T0):
    for col in columns:
        state, _ = ENGINE.apply(state, state.turn, {"type": "drop", "column": col}, now)
    return state


def test_registered_with_settings() -> None:
    game = registry.get_game("connect_four")
    assert game is not None and game.validate_settings({}) == {"bestOf": 3}
    for bad in [{"bestOf": 4}, {"x": 1}]:
        with pytest.raises(GameError):
            game.validate_settings(bad)


@pytest.mark.parametrize(
    ("moves", "cells", "last_row"),
    [
        ([0, 0, 1, 1, 2, 2, 3], [[5, 0], [5, 1], [5, 2], [5, 3]], 5),  # across
        ([6, 5, 6, 5, 6, 5, 6], [[2, 6], [3, 6], [4, 6], [5, 6]], 2),  # down
        ([0, 1, 1, 2, 2, 3, 2, 3, 3, 6, 3], [[2, 3], [3, 2], [4, 1], [5, 0]], 2),  # rising
        ([6, 5, 5, 4, 4, 3, 4, 3, 3, 0, 3], [[2, 3], [3, 4], [4, 5], [5, 6]], 2),  # falling
    ],
)
def test_four_in_a_row_wins(moves, cells, last_row) -> None:
    state = play(new(), moves)
    assert ENGINE.status(state) == ("winner", "a")
    view = ENGINE.public_view(state)
    assert view["winningCells"] == cells and view["turn"] is None
    assert view["lastMove"] == {"row": last_row, "column": moves[-1], "playerId": "a"}


def test_full_board_is_a_draw() -> None:
    state = play(new(), DRAW)
    assert ENGINE.status(state) == ("draw", None) and ENGINE.awaiting(state) == []


def test_gravity_turns_and_errors() -> None:
    state = new(first="b")
    assert state.deadline == T0 + C4_TURN_MS and ENGINE.awaiting(state) == ["b"]
    with pytest.raises(GameError) as exc:
        ENGINE.apply(state, "a", {"type": "drop", "column": 0}, T0)
    assert exc.value.code == "NOT_YOUR_TURN"
    state = play(state, [2, 2, 2, 2, 2, 2], T0 + 5)
    assert [row[2] for row in ENGINE.public_view(state)["board"]] == [1, 2, 1, 2, 1, 2]
    assert state.deadline == T0 + 5 + C4_TURN_MS
    for bad in [{"type": "drop", "column": 2}, {"type": "drop", "column": 7},
                {"type": "drop", "column": True}, {"type": "place", "column": 0}]:  # fmt: skip
        with pytest.raises(GameError):
            ENGINE.apply(state, "b", bad, T0)
    view = ENGINE.view_for(state, "b")
    assert view["seats"] == {"a": 1, "b": 2} and view["legalMoves"] == [0, 1, 3, 4, 5, 6]
    assert ENGINE.view_for(state, "a")["legalMoves"] == []
    assert ENGINE.random_action(state, "b", random.Random(3))["column"] != 2
