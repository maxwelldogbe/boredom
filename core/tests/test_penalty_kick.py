"""Penalty kick: shot resolution, kick phases, timing, views, early finish, sudden death."""

import json
import random

import pytest

from games import registry
from games.base import GameError
from games.constants import (
    MATCH_AFK_TIMEOUTS_TO_FORFEIT,
    PENALTY_AIM_MS,
    PENALTY_DIVE_GRACE_MS,
    PENALTY_FLIGHT_MS_MAX,
    PENALTY_FLIGHT_MS_MIN,
    PENALTY_KEEPER_PAUSE_MS,
    PENALTY_POWER_SWEET_MAX,
    PENALTY_RESULT_MS,
    PENALTY_SAVE_RADIUS,
    PENALTY_WOBBLE_BASE,
)
from games.penalty_kick import (
    KEEPER_HOME,
    PenaltyKick,
    PenaltyKickEngine,
    flight_ms,
    hits_keeper,
    keeper_at,
    keeper_path,
    reach,
    real_aim,
    resolve_kick,
    wobble_sd,
)

ENGINE = PenaltyKickEngine()
PK = PenaltyKick()
T0 = 1_000_000.0
CORNER = {"x": 0.1, "y": 0.15}  # far from the keeper's home (0.5, 0.3)


class Still:
    """A stand-in rng without wobble: the ball goes exactly where it is aimed."""

    def gauss(self, mu: float, sd: float) -> float:
        return mu

    def uniform(self, low: float, high: float) -> float:
        return (low + high) / 2


def new(kicks=3, first="a"):
    settings = {"kicksPerPlayer": kicks, "keeperSpeed": "normal"}
    state = ENGINE.init("a", "b", settings, Still(), first)
    state, _ = ENGINE.tick(state, T0)
    return state


def shoot(state, aim=CORNER, power=0.5, now=T0):
    action = {"type": "shoot", "aim": dict(aim), "power": power}
    return ENGINE.apply(state, ENGINE.shooter(state), action, now)


def land(state):
    """Resolve the kick in flight and move on to the next one (or the end)."""
    state, events = ENGINE.tick(state, ENGINE.next_deadline(state))
    state, _ = ENGINE.tick(state, ENGINE.next_deadline(state))
    return state, events


def kick(state, goal: bool):
    """One kick: into the corner (goal) or straight at the idle keeper (saved)."""
    state, _ = shoot(state, CORNER if goal else {"x": 0.5, "y": 0.3})
    return land(state)


def test_registered_with_settings() -> None:
    game = registry.get_game("penalty_kick")
    defaults = {"kicksPerPlayer": 5, "keeperSpeed": "normal"}
    assert game is not None and game.validate_settings({}) == defaults
    assert PK.best_of(game.validate_settings({"kicksPerPlayer": 3})) == 1
    assert game.validate_settings({"keeperSpeed": "hard"})["keeperSpeed"] == "hard"
    for bad in [{"kicksPerPlayer": 4}, {"bestOf": 3}, {"kicksPerPlayer": True}, {"keeperSpeed": 2}]:
        with pytest.raises(GameError):
            game.validate_settings(bad)


def test_each_outcome() -> None:
    home = KEEPER_HOME
    assert resolve_kick(CORNER, 0.5, home, None) == "goal"
    assert resolve_kick(CORNER, 0.5, home, {"x": 0.15, "y": 0.2}) == "saved"
    assert resolve_kick({"x": -0.2, "y": 0.5}, 0.5, home, None) == "wide"
    assert resolve_kick({"x": 0.5, "y": 1.2}, 0.5, home, None) == "over"
    assert resolve_kick({"x": 1.01, "y": 0.5}, 0.5, home, None) == "post"
    assert resolve_kick({"x": 0.5, "y": 1.02}, 0.5, home, None) == "post"
    assert resolve_kick(CORNER, 0.1, home, None) == "fizzled"


def test_wobble_grows_above_the_sweet_spot() -> None:
    assert wobble_sd(0.2) == wobble_sd(PENALTY_POWER_SWEET_MAX) == PENALTY_WOBBLE_BASE
    assert PENALTY_WOBBLE_BASE < wobble_sd(0.9) < wobble_sd(1.0)
    spread = {
        p: max(abs(real_aim(CORNER, p, rng)["x"] - CORNER["x"]) for _ in range(200))
        for p, rng in [(0.5, random.Random(3)), (1.0, random.Random(3))]
    }
    assert spread[1.0] > 2 * spread[0.5]


def test_a_ball_hitting_the_keepers_body_is_saved() -> None:
    home = KEEPER_HOME
    head, feet, glove = {"x": 0.5, "y": 0.62}, {"x": 0.5, "y": 0.02}, {"x": 0.6, "y": 0.3}
    for spot in (head, feet, glove):
        assert hits_keeper(spot, home, None) and resolve_kick(spot, 0.9, home, None) == "saved"
    beside = {"x": 0.68, "y": 0.3}  # just past the glove
    assert not hits_keeper(beside, home, None) and resolve_kick(beside, 0.9, home, None) == "goal"
    moved = {"x": 0.68, "y": 0.3}  # the same ball against a keeper standing further right
    assert resolve_kick(beside, 0.9, moved, None) == "saved"


def test_the_body_follows_the_dive_and_slow_shots_are_easier_to_reach() -> None:
    dive = {"x": 0.15, "y": 0.2}
    assert resolve_kick(KEEPER_HOME, 0.9, KEEPER_HOME, dive) == "goal"  # dived away from it
    assert hits_keeper({"x": 0.22, "y": 0.27}, KEEPER_HOME, dive)  # the stretched arm
    assert reach(0.3) > reach(0.9) > PENALTY_SAVE_RADIUS
    edge = {"x": 0.15 + reach(0.5) * 0.95, "y": 0.2}
    assert resolve_kick(edge, 0.5, KEEPER_HOME, dive) == "saved"
    assert resolve_kick(edge, 0.99, KEEPER_HOME, dive) == "goal"


def test_keeper_patrol_is_seeded_and_faster_when_hard() -> None:
    paths = {s: keeper_path(T0, s, random.Random(5)) for s in ("easy", "normal", "hard")}
    assert paths["easy"] == keeper_path(T0, "easy", random.Random(5))
    assert paths["hard"][0] == {"at": T0, **KEEPER_HOME}
    assert paths["hard"][-1]["at"] >= T0 + PENALTY_AIM_MS
    assert paths["hard"][1] == {"at": T0 + PENALTY_KEEPER_PAUSE_MS["hard"], **KEEPER_HOME}
    first_move = {s: p[2]["at"] - p[1]["at"] for s, p in paths.items()}
    assert first_move["easy"] > first_move["normal"] > first_move["hard"]  # same first point
    for p in paths["hard"]:
        assert 0.2 <= p["x"] <= 0.8 and 0.3 <= p["y"] <= 0.36
    a, b = paths["hard"][1], paths["hard"][2]
    mid = keeper_at(paths["hard"], (a["at"] + b["at"]) / 2)
    assert mid == pytest.approx({"x": (a["x"] + b["x"]) / 2, "y": (a["y"] + b["y"]) / 2})
    assert keeper_at(paths["hard"], T0 + 10 * PENALTY_AIM_MS)["x"] == paths["hard"][-1]["x"]


def test_keeper_patrols_while_aiming_and_stops_at_the_kick() -> None:
    settings = {"kicksPerPlayer": 3, "keeperSpeed": "hard"}
    state = ENGINE.init("a", "b", settings, random.Random(9), "a")
    state, _ = ENGINE.tick(state, T0)
    path = ENGINE.public_view(state)["keeperPath"]
    assert path and path[0]["at"] == T0
    later = T0 + 3000
    state, _ = shoot(state, now=later)
    view = ENGINE.public_view(state)
    assert view["keeperPath"] is None
    assert view["flight"]["keeperSpot"] == keeper_at(path, later) != KEEPER_HOME
    state, events = land(state)
    assert events[0]["data"]["keeperSpot"] == keeper_at(path, later)


def test_flight_time_scales_with_power() -> None:
    assert flight_ms(0) == PENALTY_FLIGHT_MS_MAX and flight_ms(1) == PENALTY_FLIGHT_MS_MIN
    state, events = shoot(new(), power=1.0, now=T0 + 10)
    assert events == [{"kind": "penalty_launch", "data": {"kick": 1, "shooter": "a"}}]
    assert state.shot["arriveAt"] == T0 + 10 + PENALTY_FLIGHT_MS_MIN
    assert ENGINE.next_deadline(state) == state.shot["arriveAt"] + PENALTY_DIVE_GRACE_MS


def test_invalid_shots_and_early_dive_rejected() -> None:
    state = new()
    with pytest.raises(GameError):
        ENGINE.apply(state, "b", {"type": "dive", "x": 0.2, "y": 0.2}, T0)
    for bad in [
        {"aim": {"x": 2, "y": 0.5}, "power": 0.5},
        {"aim": {"x": 0.5, "y": 0.5}, "power": 1.5},
        {"aim": {"x": float("nan"), "y": 0.5}, "power": 0.5},
        {"aim": {"x": True, "y": 0.5}, "power": 0.5},
        {"aim": [0.5, 0.5], "power": 0.5},
    ]:
        with pytest.raises(GameError):
            ENGINE.apply(state, "a", {"type": "shoot", **bad}, T0)
    state, _ = shoot(state)
    with pytest.raises(GameError):
        shoot(state)  # already kicked


def test_only_the_first_timely_dive_counts() -> None:
    state, _ = shoot(new(), now=T0)
    arrive = state.shot["arriveAt"]
    state, _ = ENGINE.apply(state, "b", {"type": "dive", "x": 0.15, "y": 0.2}, arrive)
    state, _ = ENGINE.apply(state, "b", {"type": "dive", "x": 0.9, "y": 0.9}, arrive + 1)
    assert state.dive == {"x": 0.15, "y": 0.2, "receivedAt": arrive}
    state, events = land(state)
    assert events[0]["data"]["outcome"] == "saved"


def test_late_dive_is_ignored_and_dive_is_clamped() -> None:
    state, _ = shoot(new(), now=T0)
    late = state.shot["arriveAt"] + PENALTY_DIVE_GRACE_MS + 1
    state, _ = ENGINE.apply(state, "b", {"type": "dive", "x": 0.1, "y": 0.15}, late)
    assert state.dive is None
    state, events = land(state)
    assert events[0]["data"]["outcome"] == "goal" and events[0]["data"]["dive"] is None
    state, _ = shoot(state, now=T0)
    state, _ = ENGINE.apply(state, "a", {"type": "dive", "x": -5, "y": 9}, T0 + 1)
    assert (state.dive["x"], state.dive["y"]) == (-0.1, 1.1)


def test_phases_and_views_never_leak() -> None:
    state = new()
    aiming = json.dumps(ENGINE.public_view(state))
    assert ENGINE.public_view(state)["flight"] is None and '"to"' not in aiming
    assert ENGINE.awaiting(state) == ["a"] and ENGINE.next_deadline(state) == T0 + PENALTY_AIM_MS
    state, _ = shoot(state, now=T0 + 5)
    view = ENGINE.public_view(state)
    assert view["phase"] == "flight" and view["outcome"] is None and view["kicks"] == []
    assert view["flight"]["ball"]["to"] == CORNER and view["flight"]["graceMs"] == 250
    assert ENGINE.awaiting(state) == []
    state, events = ENGINE.tick(state, ENGINE.next_deadline(state))
    view = ENGINE.view_for(state, "a")
    assert events[0]["kind"] == "penalty_result" and events[0]["data"]["scores"] == {"a": 1, "b": 0}
    assert view["phase"] == "result" and view["outcome"] == "goal" and view["kickNo"] == 1
    assert view["shooter"] == "a" and view["yourRole"] == "shooter"
    end = ENGINE.next_deadline(state)
    assert end == state.result_until and state.result_until - PENALTY_RESULT_MS > T0
    state, _ = ENGINE.tick(state, end)
    view = ENGINE.view_for(state, "a")
    assert view["phase"] == "aiming" and view["shooter"] == "b" and view["yourRole"] == "keeper"
    assert view["kickNo"] == 2 and view["turnDeadline"] == end + PENALTY_AIM_MS


def test_early_finish_after_the_result_phase() -> None:
    state = new(kicks=3)
    for goal in (True, False, True):
        state, _ = kick(state, goal)
        assert ENGINE.status(state) == ("ongoing", None)
    state, _ = shoot(state, {"x": 0.5, "y": 0.3})  # b is saved: 2-0 with one kick left
    state, _ = ENGINE.tick(state, ENGINE.next_deadline(state))
    assert ENGINE.status(state) == ("ongoing", None) and state.phase == "result"
    state, _ = ENGINE.tick(state, ENGINE.next_deadline(state))
    assert ENGINE.status(state) == ("winner", "a") and len(state.kicks) == 4
    assert ENGINE.next_deadline(state) is None and ENGINE.awaiting(state) == []


def test_sudden_death() -> None:
    state = new(kicks=3)
    for _ in range(6):
        state, _ = kick(state, True)
    view = ENGINE.public_view(state)
    assert view["suddenDeath"] and view["scores"] == {"a": 3, "b": 3} and view["winner"] is None
    for goal in (True, True, False):  # a misses in the second pair: b can still win
        state, _ = kick(state, goal)
    assert ENGINE.status(state) == ("ongoing", None)
    state, _ = kick(state, True)
    assert ENGINE.status(state) == ("winner", "b") and state.scores == {"a": 4, "b": 5}


def series(seed=2):
    settings = PK.validate_settings({"kicksPerPlayer": 3})
    state = PK.init(["a", "b"], settings, random.Random(seed), T0)
    return state, state.matches[0]


def test_aim_timeout_takes_a_mild_shot_and_counts_as_afk() -> None:
    state, match = series()
    shooter = PK.engine.shooter(match.game)
    state, events = PK.tick(state, PK.next_deadline(state))
    assert {"kind": "autoMove", "data": {"matchId": match.id, "playerId": shooter}} in events
    assert match.game.phase == "flight" and match.game.shot["power"] == 0.5
    assert match.timeouts[shooter] == 1 and MATCH_AFK_TIMEOUTS_TO_FORFEIT > 1


def test_forfeit_mid_kick() -> None:
    state, match = series()
    shot = {"type": "shoot", "aim": CORNER, "power": 0.6}
    state, _ = PK.handle_action(state, PK.engine.shooter(match.game), shot, T0)
    keeper = PK.engine.keeper(match.game)
    state, _ = PK.forfeit(state, keeper, T0 + 100, "quit")
    assert match.winner == match.opponent(keeper) and match.reason == "forfeit"
    assert PK.is_over(state) and PK.next_deadline(state) is None


def test_full_shootout_in_the_series_ends_with_results() -> None:
    state, match = series()
    first = PK.engine.shooter(match.game)
    now, events = T0, []
    while not PK.is_over(state):
        game = match.game
        if game.phase == "aiming":
            shooter = PK.engine.shooter(game)
            aim = {"x": 0.12, "y": 0.2} if shooter == first else {"x": -0.4, "y": 0.5}  # wide
            shot = {"type": "shoot", "aim": aim, "power": 0.5}
            state, ev = PK.handle_action(state, shooter, shot, now)
        else:
            now = PK.next_deadline(state)
            state, ev = PK.tick(state, now)
        events += ev
    outcomes = [e["data"]["outcome"] for e in events if e["kind"] == "penalty_result"]
    assert outcomes == ["goal", "wide", "goal", "wide"]
    assert match.winner == first and match.reason == "score"
    assert [r["player_id"] for r in PK.get_results(state)] == [first, match.opponent(first)]
