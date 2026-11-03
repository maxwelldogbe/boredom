"""Series wrapper (games/series.py) via tic-tac-toe: matches, bracket, AFK, spectating."""

import random

import pytest

from games.base import GameError
from games.constants import MATCH_AFK_TIMEOUTS_TO_FORFEIT, MATCH_MAX_DRAWS, TTT_TURN_MS
from games.tic_tac_toe import TicTacToe

TTT = TicTacToe()
T0 = 1_000_000.0
WIN = [0, 3, 1, 4, 2]  # the first mover takes the top row
LOSE = [0, 3, 1, 4, 8, 5]  # the second mover takes the middle row
DRAW = [0, 1, 2, 4, 3, 5, 7, 6, 8]


def new(n=2, seed=1, **settings):
    players = [chr(ord("a") + i) for i in range(n)]
    return TTT.init(players, TTT.validate_settings(settings), random.Random(seed), T0)


def live(state):
    return [m for m in state.matches if m.winner is None]


def play(state, match, cells, now=T0):
    """Place `cells` in turn order; returns (state, events)."""
    events = []
    for cell in cells:
        state, ev = TTT.handle_action(state, match.game.turn, {"type": "place", "cell": cell}, now)
        events += ev
    return state, events


def win_game(state, match, winner):
    """Let `winner` take the current game: they win as first mover, or the opener throws."""
    if match.game.turn == winner:
        return play(state, match, WIN)
    return play(state, match, LOSE)


def win_match(state, match, winner):
    while match.winner is None:
        state, _ = win_game(state, match, winner)
    return state


def test_first_mover_alternates_and_best_of_majority() -> None:
    state = new(bestOf=3)
    match = state.matches[0]
    assert match.game_no == 1 and match.game.turn == match.a
    state, events = win_game(state, match, match.a)
    assert match.wins[match.a] == 1 and match.winner is None
    assert match.game_no == 2 and match.game.turn == match.b
    assert any(e["kind"] == "gameEnd" and e["data"]["winner"] == match.a for e in events)
    state, _ = win_game(state, match, match.a)
    assert match.winner == match.a and match.reason == "score" and TTT.is_over(state)


def test_best_of_one() -> None:
    state = new(bestOf=1)
    state, _ = win_game(state, state.matches[0], state.matches[0].b)
    assert state.champion == state.matches[0].b


def test_draw_replays_with_sides_swapped_then_coin_flip() -> None:
    state = new()
    match = state.matches[0]
    for n in range(1, MATCH_MAX_DRAWS):
        opener = match.game.turn
        state, _ = play(state, match, DRAW)
        assert match.draws == n and sum(match.wins.values()) == 0
        assert match.game.turn != opener and match.winner is None
    state, events = play(state, match, DRAW)
    assert match.coin_flip and match.reason == "coinFlip" and match.winner in (match.a, match.b)
    over = next(e for e in events if e["kind"] == "matchOver")
    assert over["data"]["coinFlip"] is True
    assert TTT.get_view(state, "a")["match"]["coinFlip"] is True


def test_bye_for_odd_count() -> None:
    state = new(3)
    bye = [m for m in state.matches if m.b is None]
    assert len(bye) == 1 and bye[0].winner == bye[0].a and bye[0].reason == "bye"
    assert len(live(state)) == 1 and TTT.get_view(state, bye[0].a)["phase"] == "waiting"


@pytest.mark.parametrize(
    ("n", "expected"),
    [(2, [1, 2]), (3, [1, 2, 3]), (4, [1, 2, 3, 3]), (5, [1, 2, 3, 4, 4])],
)
def test_bracket_placements(n, expected) -> None:
    state = new(n, bestOf=1)
    while not TTT.is_over(state):
        match = live(state)[0]
        state = win_match(state, match, match.a)
    results = TTT.get_results(state)
    assert [r["placement"] for r in results] == expected
    assert results[0]["player_id"] == state.champion
    assert len({r["player_id"] for r in results}) == n


def test_afk_auto_moves_then_forfeits_the_match() -> None:
    state = new()
    match = state.matches[0]
    idle = match.a
    now = T0
    for n in range(1, MATCH_AFK_TIMEOUTS_TO_FORFEIT):
        now = TTT.next_deadline(state)
        state, events = TTT.tick(state, now)
        assert match.timeouts[idle] == n
        assert sum(c is not None for c in match.game.board) == 2 * n - 1
        assert {"kind": "autoMove", "data": {"matchId": match.id, "playerId": idle}} in events
        free = next(i for i, c in enumerate(match.game.board) if c is None)
        state, _ = play(state, match, [free], now)  # the opponent moves normally
    assert TTT.next_deadline(state) == now + TTT_TURN_MS
    state, events = TTT.tick(state, now + TTT_TURN_MS)
    assert match.winner == match.b and match.reason == "afk" and state.champion == match.b


def test_a_real_move_resets_the_afk_streak() -> None:
    state = new()
    match = state.matches[0]
    state, _ = TTT.tick(state, TTT.next_deadline(state))  # a times out
    state, _ = play(state, match, [next(i for i, c in enumerate(match.game.board) if c is None)])
    assert match.timeouts[match.b] == 0 and match.timeouts[match.a] == 1
    state, _ = play(state, match, [next(i for i, c in enumerate(match.game.board) if c is None)])
    assert match.timeouts[match.a] == 0


def test_forfeit_mid_match_and_while_waiting() -> None:
    state = new(3)
    match = live(state)[0]
    waiting = next(m.a for m in state.matches if m.b is None)
    state, events = TTT.forfeit(state, match.a, T0, "quit")
    assert match.winner == match.b and match.reason == "forfeit"
    assert any(e["kind"] == "matchOver" for e in events)
    final = live(state)[0]  # round 2: match.b against the bye player
    assert set(final.players()) == {match.b, waiting} and state.bracket_round == 2
    state, _ = TTT.forfeit(state, match.a, T0, "left")  # already out: nothing changes
    assert final.winner is None
    state, _ = TTT.forfeit(state, waiting, T0, "quit")
    assert state.champion == match.b


def test_forfeit_of_a_bye_player() -> None:
    state = new(3)
    waiting = next(m.a for m in state.matches if m.b is None)
    state, _ = TTT.forfeit(state, waiting, T0, "quit")
    assert waiting not in state.alive and state.bracket_round == 1
    match = live(state)[0]
    state = win_match(state, match, match.a)
    assert state.champion == match.a


def test_spectators_watch_live_matches_without_player_data() -> None:
    state = new(5)
    first, second = live(state)
    bye = next(m.a for m in state.matches if m.b is None)
    view = TTT.get_view(state, bye)
    assert view["role"] == "spectator" and view["watching"] == first.id
    assert view["liveMatches"] == [first.id, second.id]
    assert view["match"]["game"] == TTT.engine.public_view(first.game)
    assert "legalMoves" not in view["match"]["game"] and "isYourTurn" not in view["match"]["game"]
    state, events = TTT.handle_action(state, bye, {"type": "watch", "matchId": second.id}, T0)
    assert events == [] and TTT.get_view(state, bye)["watching"] == second.id
    for pid, match_id in ((first.a, second.id), (bye, "nope")):
        with pytest.raises(GameError) as exc:
            TTT.handle_action(state, pid, {"type": "watch", "matchId": match_id}, T0)
        assert exc.value.code == "INVALID_ACTION"
    player = TTT.get_view(state, first.a)
    assert player["role"] == "player" and player["watching"] is None
    assert player["match"]["id"] == first.id and "legalMoves" in player["match"]["game"]
    state = win_match(state, second, second.a)  # watched match ends: back to a live one
    assert TTT.get_view(state, bye)["watching"] == first.id
    assert TTT.get_view(state, second.b)["phase"] == "out"
