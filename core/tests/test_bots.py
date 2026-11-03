"""Bot choosers (bots/): legal moves, wins and blocks, tic-tac-toe hard never loses, budget."""

import random
import time

import pytest

from bots import connect_four as c4_bot
from bots import tic_tac_toe as ttt_bot
from games.connect_four import ConnectFourEngine
from games.tic_tac_toe import TicTacToeEngine

TTT, C4 = TicTacToeEngine(), ConnectFourEngine()
DIFFICULTIES = ("easy", "medium", "hard")


def ttt_view(cells: str, me: str = "b") -> dict:
    """A view for seat `me` from a 9-char board: x = seat a (X), o = seat b (O), . empty."""
    state = TTT.init("a", "b", {}, random.Random(0), me)
    state.board = [{"x": "a", "o": "b"}.get(ch) for ch in cells]
    state.turn = me
    return TTT.view_for(state, me)


def c4_view(rows: list[str], me: str = "b") -> dict:
    """Rows top to bottom; 1 = seat a, 2 = seat b, . empty."""
    state = C4.init("a", "b", {}, random.Random(0), me)
    state.board = [[{"1": "a", "2": "b"}.get(ch) for ch in row] for row in rows]
    state.turn = me
    return C4.view_for(state, me)


@pytest.mark.parametrize("difficulty", DIFFICULTIES)
def test_moves_are_always_legal(difficulty: str) -> None:
    rng = random.Random(7)
    for engine, choose in ((TTT, ttt_bot.choose), (C4, c4_bot.choose)):
        for _ in range(15):
            state = engine.init("a", "b", {}, rng, rng.choice(["a", "b"]))
            while engine.status(state)[0] == "ongoing":
                player = state.turn
                if player == "b":
                    view = engine.view_for(state, "b")
                    action = choose(view, rng, difficulty, 50)
                    key = "cell" if engine is TTT else "column"
                    assert action[key] in view["legalMoves"]
                else:
                    action = engine.random_action(state, "a", rng)
                state, _ = engine.apply(state, player, action, 0)


def test_ttt_medium_takes_a_win_and_blocks() -> None:
    rng = random.Random(1)
    assert ttt_bot.choose(ttt_view("oo.xx...."), rng, "medium", 50)["cell"] == 2  # win first
    assert ttt_bot.choose(ttt_view("xx..o...."), rng, "medium", 50)["cell"] == 2  # block


def test_ttt_hard_never_loses_against_any_line(monkeypatch) -> None:
    monkeypatch.setattr(ttt_bot, "HARD_SLIP", 0.0)  # the deliberate slip is tested apart
    games = 0

    def play(state) -> None:
        nonlocal games
        result, winner = TTT.status(state)
        if result != "ongoing":
            assert winner != "a"
            games += 1
            return
        if state.turn == "b":
            cell = ttt_bot.choose(TTT.view_for(state, "b"), random.Random(0), "hard", 200)["cell"]
            moves = [cell]
        else:
            moves = [i for i, v in enumerate(state.board) if v is None]
        for cell in moves:
            nxt = TTT.init("a", "b", {}, random.Random(0), state.first)
            nxt.board, nxt.turn = list(state.board), state.turn
            nxt, _ = TTT.apply(nxt, state.turn, {"type": "place", "cell": cell}, 0)
            play(nxt)

    for first in ("a", "b"):
        play(TTT.init("a", "b", {}, random.Random(0), first))
    assert games > 100


@pytest.mark.parametrize("difficulty", DIFFICULTIES)
def test_c4_takes_a_win_and_blocks(difficulty: str) -> None:
    rng = random.Random(3)
    win = c4_view([".......", ".......", ".......", ".......", "1......", "1222..1"])
    assert c4_bot.choose(win, rng, difficulty, 200)["column"] == 4
    block = c4_view([".......", ".......", ".......", "1......", "12.....", "12.2..."])
    assert c4_bot.choose(block, rng, difficulty, 200)["column"] == 0


@pytest.mark.parametrize("difficulty", ("medium", "hard"))
def test_c4_search_respects_the_budget(difficulty: str) -> None:
    view = c4_view([".......", ".......", ".......", ".......", "...2...", "..112.."])
    for budget in (20, 100):
        start = time.perf_counter()
        action = c4_bot.choose(view, random.Random(0), difficulty, budget)
        elapsed = (time.perf_counter() - start) * 1000
        assert action["column"] in view["legalMoves"]
        assert elapsed < budget * 1.5 + 20
