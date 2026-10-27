"""Dots and Boxes module: pure calls with injected time."""

import json
import random

import pytest

from games import registry
from games.base import GameError
from games.constants import DOTS_TURN_MS, OFFLINE_FORFEIT_MS
from games.dots_and_boxes import DotsAndBoxes, all_lines, box_sides

DB = DotsAndBoxes()
T0 = 3_000_000.0


def new(players=("a", "b"), size=4, seed=1):
    state = DB.init(list(players), DB.validate_settings({"size": size}), random.Random(seed), T0)
    state.order = list(players)  # scripted positions assume seat order; shuffle tested below
    return state


def test_turn_order_is_a_random_shuffle() -> None:
    players = ["a", "b", "c", "d"]
    orders = set()
    for seed in range(30):
        state = DB.init(players, DB.validate_settings({}), random.Random(seed), T0)
        assert sorted(state.order) == players and state.turn_index == 0
        orders.add(tuple(state.order))
    assert len({o[0] for o in orders}) == 4 and len(orders) > 4


def draw(state, line, pid=None, now=T0):
    return DB.handle_action(state, pid or state.current, {"type": "drawLine", "id": line}, now)[0]


def preset(state, lines, owner=0):
    """Mark lines as drawn without turn logic, to build positions quickly."""
    for line in lines:
        state.lines[line] = owner
    return state


def test_registered_and_settings() -> None:
    assert isinstance(registry.get_game("dots_and_boxes"), DotsAndBoxes)
    assert DB.validate_settings({}) == {"size": 5}
    for bad in (3, 8, "5", True, 5.0, None):
        with pytest.raises(GameError):
            DB.validate_settings({"size": bad})
    with pytest.raises(GameError):
        DB.validate_settings({"rounds": 3})
    assert (DB.min_players, DB.max_players) == (2, 4)


@pytest.mark.parametrize("size", [4, 5, 6, 7])
def test_line_ids_cover_the_board(size) -> None:
    lines = all_lines(size)
    assert len(lines) == len(set(lines)) == 2 * size * (size + 1)
    assert f"h:{size}:{size - 1}" in lines and f"v:{size - 1}:{size}" in lines
    state = new(size=size)
    for line in (f"h:{size + 1}:0", f"h:0:{size}", f"v:{size}:0", f"v:0:{size + 1}"):
        with pytest.raises(GameError) as exc:
            draw(state, line)
        assert exc.value.code == "INVALID_ACTION"


@pytest.mark.parametrize("bad", ["x:0:0", "h-0-0", "h:0", "h:a:0", "", None, 7, "h:-1:0"])
def test_unknown_line_rejected(bad) -> None:
    with pytest.raises(GameError) as exc:
        draw(new(), bad)
    assert exc.value.code == "INVALID_ACTION"


def test_drawn_out_of_turn_and_unknown_action_rejected() -> None:
    state = draw(new(), "h:0:0")
    with pytest.raises(GameError) as exc:
        draw(state, "h:0:0")
    assert exc.value.code == "INVALID_ACTION"
    with pytest.raises(GameError) as exc:
        draw(state, "h:0:1", pid="a")
    assert exc.value.code == "NOT_YOUR_TURN"
    with pytest.raises(GameError):
        DB.handle_action(state, "b", {"type": "pass"}, T0)
    with pytest.raises(GameError):
        DB.handle_action(state, "zed", {"type": "drawLine", "id": "h:0:1"}, T0)


def test_turn_passes_without_a_box() -> None:
    state = new(("a", "b", "c"))
    assert state.current == "a"
    state = draw(state, "h:0:0")
    assert state.current == "b" and state.turn_deadline == T0 + DOTS_TURN_MS
    state = draw(state, "h:4:3", now=T0 + 5)
    assert state.current == "c" and state.turn_deadline == T0 + 5 + DOTS_TURN_MS


@pytest.mark.parametrize("last", range(4))
def test_box_completion_on_each_side_keeps_the_turn(last) -> None:
    sides = box_sides(1, 1)
    state = preset(new(), [s for i, s in enumerate(sides) if i != last], owner=1)
    state.turn_index = 1
    state = draw(state, sides[last])
    assert state.boxes[1][1] == 1 and state.current == "b"
    view = DB.get_view(state, "a")
    assert view["boxes"][1][1] == "b" and view["scores"] == {"a": 0, "b": 1}
    move = {"lineId": sides[last], "playerId": "b", "boxes": [[1, 1]], "auto": None}
    assert view["lastMove"] == move


def test_one_line_closes_two_boxes() -> None:
    shared = "v:0:1"  # between box (0,0) and box (0,1)
    around = set(box_sides(0, 0)) | set(box_sides(0, 1))
    state = preset(new(), around - {shared}, owner=1)
    state = draw(state, shared)
    assert state.boxes[0][0] == state.boxes[0][1] == 0
    assert DB.get_view(state, "b")["scores"] == {"a": 2, "b": 0}
    assert state.current == "a"


def finish_with(owners, closer_index, players=("a", "b", "c")):
    """A 4x4 board with every line drawn but the last; `owners` maps box -> owner index."""
    state = new(players)
    lines = all_lines(4)
    preset(state, lines[:-1])
    for (r, c), owner in owners.items():
        state.boxes[r][c] = owner
    state.turn_index = closer_index
    return draw(state, lines[-1])  # the last line closes box (3, 3)


def test_game_ends_when_all_boxes_claimed_and_results_rank_by_boxes() -> None:
    owners = {(r, c): 0 if r < 2 else 1 for r in range(4) for c in range(4) if (r, c) != (3, 3)}
    state = finish_with(owners, closer_index=2)
    assert DB.is_over(state) and state.phase == "done" and DB.next_deadline(state) is None
    assert DB.get_results(state) == [
        {"player_id": "a", "placement": 1, "score": 8},
        {"player_id": "b", "placement": 2, "score": 7},
        {"player_id": "c", "placement": 3, "score": 1},
    ]
    with pytest.raises(GameError):
        draw(state, "h:0:0", pid="a")
    view = DB.get_view(state, "a")
    assert view["currentPlayerId"] is None and view["isYourTurn"] is False


def test_tie_shares_first_place() -> None:
    owners = {(r, c): 0 if r < 2 else 1 for r in range(4) for c in range(4) if (r, c) != (3, 3)}
    state = finish_with(owners, closer_index=1, players=("a", "b"))
    assert {r["player_id"]: r["placement"] for r in DB.get_results(state)} == {"a": 1, "b": 1}


def test_timeout_auto_draws_a_safe_line() -> None:
    state = new()
    # Box (0,0) has two sides; its other two sides are unsafe. Everything else is safe.
    preset(state, ["h:0:0", "v:0:0"], owner=1)
    assert DB.next_deadline(state) == T0 + DOTS_TURN_MS
    state, events = DB.tick(state, T0 + DOTS_TURN_MS - 1)
    assert len(state.lines) == 2 and events == []
    state, _ = DB.tick(state, T0 + DOTS_TURN_MS)
    move = state.last_move
    assert move["playerId"] == "a" and move["auto"] == "timeout"
    assert move["lineId"] not in ("h:1:0", "v:0:1")
    assert state.current == "b" and state.turn_deadline == T0 + 2 * DOTS_TURN_MS


def test_auto_move_falls_back_to_unsafe_line_when_no_safe_one() -> None:
    state = new()
    lines = all_lines(4)
    # Draw everything except two lines of box (0,0): both remaining lines are unsafe.
    keep = {"h:1:0", "v:0:1"}
    preset(state, [line for line in lines if line not in keep], owner=1)
    for r in range(4):
        for c in range(4):
            if (r, c) not in ((0, 0), (0, 1), (1, 0)):
                state.boxes[r][c] = 1
    state, _ = DB.tick(state, T0 + DOTS_TURN_MS)
    assert state.last_move["lineId"] in keep and state.last_move["auto"] == "timeout"


def test_offline_alone_changes_nothing_before_the_turn_timeout() -> None:
    state = new()
    state, _ = DB.on_presence(state, "a", False, T0)
    assert DB.next_deadline(state) == T0 + DOTS_TURN_MS
    state, _ = DB.tick(state, T0 + OFFLINE_FORFEIT_MS)
    assert state.lines == {} and state.current == "a"


@pytest.mark.parametrize("reason", ["quit", "left", "offline"])
def test_forfeit_on_your_turn_passes_it_on(reason) -> None:
    state = draw(new(("a", "b", "c")), "h:0:0")  # b's turn
    state, events = DB.forfeit(state, "b", T0 + 500, reason)
    assert events == [] and state.current == "c"
    assert state.turn_deadline == T0 + 500 + DOTS_TURN_MS
    state = draw(state, "h:0:1", now=T0 + 600)
    assert state.current == "a"  # b is skipped from now on
    state = draw(state, "h:0:2", now=T0 + 700)
    assert state.current == "c"
    with pytest.raises(GameError):
        draw(state, "h:0:3", pid="b")


def test_forfeit_off_turn_keeps_the_turn_and_the_board() -> None:
    state = new(("a", "b", "c"))
    sides = box_sides(0, 0)
    for line in sides[:3]:
        state = draw(state, line)
    assert state.current == "a"
    state = draw(state, sides[3])  # a closes (0,0) and keeps the turn
    state, _ = DB.forfeit(state, "c", T0 + 1, "quit")
    assert state.current == "a" and state.turn_deadline == T0 + DOTS_TURN_MS
    view = DB.get_view(state, "a")
    assert view["boxes"][0][0] == "a" and view["lines"][sides[1]] == "b"
    assert view["order"] == ["a", "b", "c"] and view["scores"]["a"] == 1


def test_forfeiters_lines_and_boxes_stay() -> None:
    state = new(("a", "b", "c"))
    sides = box_sides(0, 0)
    state = draw(state, sides[0])
    state = draw(state, sides[1])
    state = draw(state, sides[2])
    state = draw(state, sides[3], pid="a")  # a closes it
    state, _ = DB.forfeit(state, "a", T0 + 1, "left")
    assert state.boxes[0][0] == 0 and state.lines[sides[0]] == 0
    assert DB.get_results(state)[0] == {"player_id": "a", "placement": 1, "score": 1}
    assert state.current == "b"


def test_timeouts_play_out_to_the_end_and_repeat_with_the_same_seed() -> None:
    def play(seed):
        state = new(("a", "b", "c"), size=4, seed=seed)
        while not DB.is_over(state):
            state, _ = DB.tick(state, DB.next_deadline(state))
        return state

    first = play(7)
    assert len(first.lines) == len(all_lines(4)) and first.lines == play(7).lines
    assert sum(r["score"] for r in DB.get_results(first)) == 16


def test_view_is_public_and_serializable() -> None:
    state = draw(new(("a", "b", "c")), "v:2:4")
    view = DB.get_view(state, "b")
    json.dumps(view)
    assert view == {
        "phase": "playing",
        "size": 4,
        "order": ["a", "b", "c"],
        "currentPlayerId": "b",
        "isYourTurn": True,
        "lines": {"v:2:4": "a"},
        "boxes": [[None] * 4 for _ in range(4)],
        "scores": {"a": 0, "b": 0, "c": 0},
        "lastMove": {"lineId": "v:2:4", "playerId": "a", "boxes": [], "auto": None},
        "turnDeadline": T0 + DOTS_TURN_MS,
    }
    assert DB.get_view(state, "a")["isYourTurn"] is False
