"""Rock-Paper-Scissors module: pure calls with seeded rng and injected time."""

import json
import random
from itertools import product

import pytest

from games import registry
from games.base import GameError
from games.constants import OFFLINE_FORFEIT_MS, RPS_PICK_TIMEOUT_MS, RPS_REVEAL_MS
from games.rps import RockPaperScissors

RPS = RockPaperScissors()
T0 = 1_000_000.0


def new(players=("a", "b"), seed=1, **settings):
    full = RPS.validate_settings(settings)
    return RPS.init(list(players), full, random.Random(seed), T0)


def pick(state, pid, choice, now=T0):
    state, events = RPS.handle_action(state, pid, {"type": "pick", "choice": choice}, now)
    return state, events


def match_of(state, pid):
    return next(m for m in state.matches if pid in m.players())


def play_round(state, a_choice, b_choice, a="a", b="b", now=T0):
    """Both pick, then the reveal pause ends. Returns (state, all events, time after)."""
    state, ev1 = pick(state, a, a_choice, now)
    state, ev2 = pick(state, b, b_choice, now)
    now = now + RPS_REVEAL_MS
    state, ev3 = RPS.tick(state, now)
    return state, ev1 + ev2 + ev3, now


def test_registered() -> None:
    assert registry.get_game("rps") is not None


def test_settings() -> None:
    assert RPS.validate_settings({}) == {"bestOf": 3, "mode": "duel"}
    assert RPS.validate_settings({"bestOf": 5, "mode": "bracket"})["bestOf"] == 5
    for bad in [{"bestOf": 4}, {"bestOf": True}, {"bestOf": "3"}, {"mode": "x"}, {"x": 1}]:
        with pytest.raises(GameError):
            RPS.validate_settings(bad)


def test_two_players_force_duel_and_duel_needs_two() -> None:
    assert new(mode="bracket").mode == "duel"
    with pytest.raises(GameError) as exc:
        new(("a", "b", "c"), mode="duel")
    assert exc.value.code == "INVALID_ACTION"


@pytest.mark.parametrize(("pa", "pb"), list(product(["rock", "paper", "scissors"], repeat=2)))
def test_all_nine_combinations(pa, pb) -> None:
    beats = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
    state = new()
    m = match_of(state, "a")
    first, second = m.a, m.b
    state, _ = pick(state, first, pa)
    assert m.phase == "picking"
    state, events = pick(state, second, pb)
    reveal = next(e for e in events if e["kind"] == "reveal")["data"]
    expected = None if pa == pb else (first if beats[pa] == pb else second)
    assert reveal["roundWinner"] == expected
    assert reveal["picks"] == {first: pa, second: pb}
    assert m.phase == "reveal" and m.deadline == T0 + RPS_REVEAL_MS
    assert sum(m.scores.values()) == (0 if expected is None else 1)


def test_tie_replays_without_counting() -> None:
    state = new()
    state, _, now = play_round(state, "rock", "rock")
    m = state.matches[0]
    assert m.round == 2 and m.phase == "picking" and m.scores == {"a": 0, "b": 0}
    assert m.picks == {"a": None, "b": None}
    assert m.deadline == now + RPS_PICK_TIMEOUT_MS


def test_timeout_non_picker_loses_round() -> None:
    state = new()
    state, _ = pick(state, "a", "paper")
    assert RPS.next_deadline(state) == T0 + RPS_PICK_TIMEOUT_MS
    state, events = RPS.tick(state, T0 + RPS_PICK_TIMEOUT_MS - 1)
    assert events == []
    state, events = RPS.tick(state, T0 + RPS_PICK_TIMEOUT_MS)
    assert events[0]["data"]["roundWinner"] == "a"
    assert state.matches[0].scores == {"a": 1, "b": 0}


def test_timeout_nobody_picks_is_a_tie() -> None:
    state = new()
    state, events = RPS.tick(state, T0 + RPS_PICK_TIMEOUT_MS)
    assert events[0]["data"]["roundWinner"] is None
    assert state.matches[0].scores == {"a": 0, "b": 0}


@pytest.mark.parametrize(("best_of", "needed"), [(3, 2), (5, 3)])
def test_first_to_majority_wins_duel(best_of, needed) -> None:
    state = new(bestOf=best_of)
    now = T0
    for _ in range(needed):
        assert not RPS.is_over(state)
        state, events, now = play_round(state, "rock", "scissors", now=now)
    assert RPS.is_over(state) and state.champion == "a"
    assert any(e["kind"] == "matchOver" and e["data"]["reason"] == "score" for e in events)
    assert RPS.next_deadline(state) is None
    assert RPS.get_results(state) == [
        {"player_id": "a", "placement": 1, "points": 3},
        {"player_id": "b", "placement": 2, "points": 2},
    ]


def test_invalid_actions() -> None:
    state = new(("a", "b", "c"), mode="bracket")
    bye = next(m for m in state.matches if m.b is None).a
    m = next(m for m in state.matches if m.b is not None)
    for pid, action, code in [
        (m.a, {"type": "shoot"}, "INVALID_ACTION"),
        (m.a, {"type": "pick", "choice": "lizard"}, "INVALID_ACTION"),
        (bye, {"type": "pick", "choice": "rock"}, "NOT_YOUR_TURN"),
    ]:
        with pytest.raises(GameError) as exc:
            RPS.handle_action(state, pid, action, T0)
        assert exc.value.code == code
    state, _ = pick(state, m.a, "rock")
    with pytest.raises(GameError) as exc:
        pick(state, m.a, "paper")
    assert exc.value.code == "INVALID_ACTION"
    state, _ = pick(state, m.b, "rock")
    with pytest.raises(GameError) as exc:
        pick(state, m.a, "paper")  # during reveal
    assert exc.value.code == "NOT_YOUR_TURN"


def test_odd_players_get_a_bye_and_advance() -> None:
    state = new(("a", "b", "c"), mode="bracket", seed=3)
    assert len(state.matches) == 2
    bye = next(m for m in state.matches if m.b is None)
    assert bye.phase == "over" and bye.winner == bye.a and bye.a in state.alive
    real = next(m for m in state.matches if m.b is not None)
    state, events, _ = play_round(state, "rock", "scissors", real.a, real.b)
    state, events, _ = play_round(state, "rock", "scissors", real.a, real.b, now=T0 + 10_000)
    assert state.bracket_round == 2
    assert {state.matches[0].a, state.matches[0].b} == {real.a, bye.a}
    assert any(e["kind"] == "bracketRound" for e in events)


def play_bracket_to_end(state, now=T0):
    """First-listed player of every live match wins every round."""
    while not RPS.is_over(state):
        for m in state.matches:
            if m.phase == "picking":
                state, _ = pick(state, m.a, "rock", now)
                state, _ = pick(state, m.b, "scissors", now)
        now += RPS_REVEAL_MS
        state, _ = RPS.tick(state, now)
    return state


def test_bracket_placements_and_points() -> None:
    players = ["p1", "p2", "p3", "p4", "p5"]
    state = play_bracket_to_end(new(players, mode="bracket", seed=7))
    results = {r["player_id"]: r for r in RPS.get_results(state)}
    final = state.bracket_round
    assert final == 3  # 5 -> 3 -> 2 -> 1
    champ = state.champion
    assert results[champ] == {"player_id": champ, "placement": 1, "points": 3}
    runner = next(p for p, r in state.out_round.items() if r == final)
    assert results[runner]["placement"] == 2 and results[runner]["points"] == 2
    semis = [p for p, r in state.out_round.items() if r == final - 1]
    firsts = [p for p, r in state.out_round.items() if r == 1]
    assert len(semis) == 1 and len(firsts) == 2
    assert results[semis[0]]["placement"] == 3 and results[semis[0]]["points"] == 1
    for p in firsts:
        assert results[p]["placement"] == 4 and results[p]["points"] == 0
    assert [r["placement"] for r in RPS.get_results(state)] == [1, 2, 3, 4, 4]


def test_bracket_with_four_players_shares_semifinal_place() -> None:
    state = play_bracket_to_end(new(["a", "b", "c", "d"], mode="bracket", seed=2))
    placements = sorted(r["placement"] for r in RPS.get_results(state))
    points = sorted((r["points"] for r in RPS.get_results(state)), reverse=True)
    assert placements == [1, 2, 3, 3] and points == [3, 2, 1, 1]


def test_seeded_pairing_is_deterministic() -> None:
    pairs = lambda s: [(m.a, m.b) for m in s.matches]  # noqa: E731
    players = ["a", "b", "c", "d", "e", "f"]
    assert pairs(new(players, mode="bracket", seed=5)) == pairs(
        new(players, mode="bracket", seed=5)
    )


def test_offline_forfeit_after_30s() -> None:
    state = new()
    state, _ = RPS.on_presence(state, "b", False, T0)
    assert RPS.next_deadline(state) == T0 + RPS_PICK_TIMEOUT_MS
    now = T0
    while not RPS.is_over(state):  # replays of timed-out rounds until forfeit
        now = RPS.next_deadline(state)
        state, events = RPS.tick(state, now)
    assert now == T0 + OFFLINE_FORFEIT_MS
    assert state.champion == "a"
    assert any(e["data"].get("reason") == "forfeit" for e in events)


def test_reconnect_cancels_forfeit() -> None:
    state = new()
    state, _ = RPS.on_presence(state, "b", False, T0)
    state, _ = RPS.on_presence(state, "b", True, T0 + 5_000)
    state, _ = RPS.tick(state, T0 + OFFLINE_FORFEIT_MS)
    assert not RPS.is_over(state)


def test_both_offline_later_leaver_wins() -> None:
    state = new()
    state, _ = RPS.on_presence(state, "a", False, T0)
    state, _ = RPS.on_presence(state, "b", False, T0 + 1_000)
    state, _ = RPS.tick(state, T0 + OFFLINE_FORFEIT_MS + 1_000)
    assert state.champion == "b"


def test_view_hides_opponent_pick_until_reveal() -> None:
    state = new()
    state, _ = pick(state, "a", "scissors")
    view_b = RPS.get_view(state, "b")
    assert "scissors" not in json.dumps(view_b)
    assert view_b["matches"][0]["hasPicked"] == {"a": True, "b": False}
    assert view_b["myPick"] is None and view_b["phase"] == "picking"
    assert RPS.get_view(state, "a")["myPick"] == "scissors"
    state, _ = pick(state, "b", "rock")
    revealed = RPS.get_view(state, "b")
    assert revealed["phase"] == "reveal"
    assert revealed["matches"][0]["lastReveal"]["picks"] == {"a": "scissors", "b": "rock"}


def test_spectator_view_never_contains_live_picks() -> None:
    state = new(("a", "b", "c"), mode="bracket", seed=3)
    real = next(m for m in state.matches if m.b is not None)
    bye = next(m for m in state.matches if m.b is None).a
    state, _ = pick(state, real.a, "paper")
    view = RPS.get_view(state, bye)
    assert "paper" not in json.dumps(view)
    assert view["phase"] == "matchOver" and view["myPick"] is None


def test_view_shape_is_json_serializable() -> None:
    view = RPS.get_view(new(), "a")
    assert set(view) == {
        "phase",
        "mode",
        "bestOf",
        "bracketRound",
        "myMatch",
        "myPick",
        "matches",
        "alive",
        "eliminated",
        "champion",
    }
    json.dumps(view)
