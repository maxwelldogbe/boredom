"""Checkers engine and its series game: setup, moves, captures, kings, endings, settings, views."""

import random

import pytest

from games import registry
from games.base import GameError
from games.checkers import Checkers, CheckersEngine, legal_moves
from games.constants import CHECKERS_DRAW_PLIES, CHECKERS_TURN_MS

ENGINE = CheckersEngine()
CHECKERS = Checkers()
T0 = 1_000_000.0


def new(pieces=None, flying=False, backward=False, turn="a"):
    """a is seat 1, b seat 2. `pieces` maps (r, c) -> (seat, king) on an otherwise empty board."""
    settings = {"flyingKings": flying, "backwardCapture": backward}
    state = ENGINE.init("a", "b", settings, random.Random(1), turn)
    if pieces is not None:
        state.board = [[None] * 8 for _ in range(8)]
        for (r, c), (seat, king) in pieces.items():
            state.board[r][c] = {"seat": seat, "king": king}
    state, _ = ENGINE.tick(state, T0)
    return state


def move(state, src, dst, player=None, now=T0):
    action = {"type": "move", "from": list(src), "to": list(dst)}
    state, _ = ENGINE.apply(state, player or state.turn, action, now)
    return state


def targets(state, seat=None):
    seat = seat or state.seat_of(state.turn)
    return sorted((tuple(m["from"]), tuple(m["to"])) for m in legal_moves(state, seat))


def test_registered_with_settings() -> None:
    game = registry.get_game("checkers")
    assert game is not None and game.min_players == 2 and game.max_players == 10
    assert game.validate_settings({}) == {
        "bestOf": 1, "flyingKings": False, "backwardCapture": False,
    }  # fmt: skip
    assert game.validate_settings({"bestOf": 3, "flyingKings": True})["bestOf"] == 3
    for bad in [{"bestOf": 5}, {"flyingKings": 1}, {"backwardCapture": "yes"}, {"x": 1}]:
        with pytest.raises(GameError):
            game.validate_settings(bad)


def test_initial_setup() -> None:
    state = new()
    pieces = [(r, c, p) for r, row in enumerate(state.board) for c, p in enumerate(row) if p]
    assert len(pieces) == 24 and all((r + c) % 2 == 1 for r, c, _ in pieces)
    assert all(p["seat"] == 2 for r, _, p in pieces if r < 3)
    assert all(p["seat"] == 1 for r, _, p in pieces if r > 4)
    assert not any(p["king"] for _, _, p in pieces)
    view = ENGINE.view_for(state, "a")
    assert view["turn"] == "a" and len(view["legalMoves"]) == 7
    assert all(m["from"][0] == 5 and m["to"][0] == 4 for m in view["legalMoves"])


def test_simple_moves_and_errors() -> None:
    state = new()
    with pytest.raises(GameError) as exc:
        move(state, (2, 1), (3, 0), player="b")
    assert exc.value.code == "NOT_YOUR_TURN"
    for src, dst in [((5, 0), (4, 0)), ((5, 0), (3, 2)), ((6, 1), (5, 0)), ((5, 0), (6, 1))]:
        with pytest.raises(GameError) as exc:
            move(state, src, dst)
        assert exc.value.code == "INVALID_ACTION"
    state = move(state, (5, 0), (4, 1), now=T0 + 7)
    assert state.board[4][1] == {"seat": 1, "king": False} and state.board[5][0] is None
    assert state.turn == "b" and state.deadline == T0 + 7 + CHECKERS_TURN_MS
    assert ENGINE.public_view(state)["lastMove"] == {
        "from": [5, 0], "to": [4, 1], "captures": [], "playerId": "a", "crowned": False,
    }  # fmt: skip
    state = move(state, (2, 1), (3, 0))  # seat 2 moves down
    assert state.turn == "a"


def test_capture_is_mandatory() -> None:
    state = new({(5, 2): (1, False), (5, 6): (1, False), (4, 3): (2, False), (0, 7): (2, False)})
    assert targets(state) == [((5, 2), (3, 4))]
    assert all(m["captures"] for m in ENGINE.view_for(state, "a")["legalMoves"])
    with pytest.raises(GameError):
        move(state, (5, 6), (4, 7))
    state = move(state, (5, 2), (3, 4))
    assert state.board[4][3] is None and state.turn == "b"


def test_multi_jump_keeps_the_turn_and_the_piece() -> None:
    pieces = {(6, 1): (1, False), (7, 6): (1, False), (5, 2): (2, False), (3, 4): (2, False)}
    state = new({**pieces, (0, 7): (2, False)})
    state = move(state, (6, 1), (4, 3), now=T0 + 3)
    assert state.turn == "a" and state.deadline == T0 + 3 + CHECKERS_TURN_MS
    view = ENGINE.view_for(state, "a")
    assert view["forcedPiece"] == [4, 3]
    assert view["legalMoves"] == [{"from": [4, 3], "to": [2, 5], "captures": [[3, 4]]}]
    with pytest.raises(GameError):
        move(state, (7, 6), (6, 5))
    state = move(state, (4, 3), (2, 5))
    assert state.turn == "b" and state.forced is None and state.board[3][4] is None


def test_crowning_ends_the_turn_even_with_another_jump() -> None:
    state = new({(2, 1): (1, False), (1, 2): (2, False), (1, 4): (2, False)})
    state = move(state, (2, 1), (0, 3))
    assert state.board[0][3] == {"seat": 1, "king": True}
    assert state.turn == "b" and state.forced is None
    assert ENGINE.public_view(state)["lastMove"]["crowned"] is True


def test_king_moves_and_captures_one_square_any_direction() -> None:
    state = new({(4, 3): (1, True), (0, 7): (2, False)})
    assert targets(state) == [((4, 3), to) for to in [(3, 2), (3, 4), (5, 2), (5, 4)]]
    state = new({(4, 3): (1, True), (5, 4): (2, False), (0, 7): (2, False)})
    assert targets(state) == [((4, 3), (6, 5))]  # backward capture, and it is mandatory
    state = move(state, (4, 3), (6, 5))
    assert state.board[5][4] is None


def test_no_legal_move_loses() -> None:
    blocked = {(0, 1): (2, False), (1, 0): (1, False), (1, 2): (1, False), (2, 3): (1, False)}
    state = new({**blocked, (7, 6): (1, False)})
    state = move(state, (7, 6), (6, 7))
    assert ENGINE.status(state) == ("winner", "a") and ENGINE.awaiting(state) == []
    assert state.deadline is None


def test_no_pieces_loses() -> None:
    state = new({(5, 2): (1, False), (4, 3): (2, False)})
    state = move(state, (5, 2), (3, 4))
    assert ENGINE.status(state) == ("winner", "a")


def test_draw_counter() -> None:
    kings = {(7, 0): (1, True), (0, 7): (2, True), (6, 7): (1, False), (1, 0): (2, False)}
    state = new(kings)
    state.quiet_plies = 5
    state = move(state, (7, 0), (6, 1))  # king move: counts
    assert state.quiet_plies == 6
    state = move(state, (1, 0), (2, 1))  # man move: resets
    assert state.quiet_plies == 0
    state = new({(5, 2): (1, True), (4, 3): (2, False), (0, 7): (2, True)})
    state.quiet_plies = 9
    state = move(state, (5, 2), (3, 4))  # capture: resets
    assert state.quiet_plies == 0
    state = new(kings)
    state.quiet_plies = CHECKERS_DRAW_PLIES - 1
    state = move(state, (7, 0), (6, 1))
    assert ENGINE.status(state) == ("draw", None) and ENGINE.public_view(state)["draw"] is True


def test_flying_kings_setting() -> None:
    open_diag = {(7, 0): (1, True), (0, 1): (2, False)}
    assert len(targets(new(open_diag, flying=False))) == 1
    assert len(targets(new(open_diag, flying=True))) == 7
    far = {(7, 0): (1, True), (3, 4): (2, False), (0, 1): (2, False)}
    assert targets(new(far, flying=False)) == [((7, 0), (6, 1))]
    flying = new(far, flying=True)
    assert targets(flying) == [((7, 0), (0, 7)), ((7, 0), (1, 6)), ((7, 0), (2, 5))]
    flying = move(flying, (7, 0), (1, 6))
    assert flying.board[3][4] is None and flying.board[1][6]["king"]


def test_backward_capture_setting() -> None:
    pieces = {(3, 2): (1, False), (4, 3): (2, False), (7, 0): (2, False)}
    assert targets(new(pieces, backward=False)) == [((3, 2), (2, 1)), ((3, 2), (2, 3))]
    assert targets(new(pieces, backward=True)) == [((3, 2), (5, 4))]


def test_random_auto_moves_are_always_legal() -> None:
    for seed in range(6):
        rng = random.Random(seed)
        state = new(flying=seed % 2 == 1, backward=seed % 3 == 0)
        for _ in range(400):
            if ENGINE.status(state)[0] != "ongoing":
                break
            action = ENGINE.random_action(state, state.turn, rng)
            state, _ = ENGINE.apply(state, state.turn, action, T0)  # raises if illegal


def test_series_views_and_timeout() -> None:
    state = CHECKERS.init(["a", "b", "c"], CHECKERS.validate_settings({}), random.Random(3), T0)
    match = next(m for m in state.matches if m.winner is None)
    bye = next(m.a for m in state.matches if m.b is None)
    mover, other = match.game.turn, match.opponent(match.game.turn)
    assert "legalMoves" in CHECKERS.get_view(state, mover)["match"]["game"]
    assert "legalMoves" not in CHECKERS.get_view(state, other)["match"]["game"]
    assert "legalMoves" not in CHECKERS.get_view(state, bye)["match"]["game"]
    state, events = CHECKERS.tick(state, CHECKERS.next_deadline(state))
    assert any(e["kind"] == "autoMove" for e in events) and match.game.turn == other


def test_full_bracket_game() -> None:
    rng = random.Random(7)
    state = CHECKERS.init(["a", "b", "c"], CHECKERS.validate_settings({}), random.Random(7), T0)
    for _ in range(5000):
        if CHECKERS.is_over(state):
            break
        match = next(m for m in state.matches if m.winner is None)
        action = CHECKERS.engine.random_action(match.game, match.game.turn, rng)
        state, _ = CHECKERS.handle_action(state, match.game.turn, action, T0)
    results = CHECKERS.get_results(state)
    assert [r["placement"] for r in results] == [1, 2, 3]
    assert results[0]["player_id"] == state.champion and results[0]["score"] == 2 - (
        state.champion in state.byes
    )
