"""Penalty kick: a shootout as a MatchEngine, one shootout per match in a bracket
(games/series.py).

Each kick one player shoots and the other keeps goal; the first mover shoots first and the
roles swap every kick. Positions are in the goal plane seen from behind the shooter: x from
0 (left post) to 1 (right post), y from 0 (ground) to 1 (crossbar).

A kick has three phases:
- aiming: the shooter has PENALTY_AIM_MS to shoot (aim and power). The real aim is the aim
  plus gaussian wobble (rng) that grows above PENALTY_POWER_SWEET_MAX; it is fixed and shown
  the moment the ball is kicked. The keeper cannot act yet: the keeper patrols the goal on a
  public path of random points (rng) at the `keeperSpeed` setting's pace.
- flight: the ball flies for PENALTY_FLIGHT_MS_MAX (weak) down to PENALTY_FLIGHT_MS_MIN
  (full power). The keeper stops where the patrol was at the kick (the keeper spot) and may
  dive from there until arriveAt + the dive grace (the optional `diveGraceMs` setting,
  default PENALTY_DIVE_GRACE_MS); only the first dive counts.
- result: resolved at arriveAt + grace and shown for PENALTY_RESULT_MS.
Outcomes: goal, saved, wide, over, post, fizzled; only a goal scores. A ball on target is
saved when it hits the keeper's body (the drawn figure, posed by the dive) or, after a dive,
lands within the hands' reach.

After `kicksPerPlayer` kicks each the higher score wins; the shootout ends early once one side
cannot catch up. Tied after that: sudden death, one kick each until a pair differs. The winner
is declared when the deciding kick's result phase ends, so everyone sees that kick land.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Any

from games.base import GameError, GameEvent
from games.constants import (
    PENALTY_AIM_MS,
    PENALTY_DIVE_GRACE_MS,
    PENALTY_FLIGHT_MS_MAX,
    PENALTY_FLIGHT_MS_MIN,
    PENALTY_KEEPER_PAUSE_MS,
    PENALTY_KEEPER_SPEED,
    PENALTY_POST_MARGIN,
    PENALTY_POWER_FIZZLE,
    PENALTY_POWER_SWEET_MAX,
    PENALTY_RESULT_MS,
    PENALTY_SAVE_RADIUS,
    PENALTY_SLOW_BONUS,
    PENALTY_WOBBLE_BASE,
    PENALTY_WOBBLE_WILD,
)
from games.match_engine import MatchEngine, Outcome
from games.series import SeriesGame

KEEPER_HOME = {"x": 0.5, "y": 0.3}
KEEPER_SPEEDS = tuple(PENALTY_KEEPER_SPEED)
BALL_FROM = {"x": 0.5, "y": 0.0}  # the penalty spot, straight in front of the goal centre
AIM_RANGE = (-0.5, 1.5)
DIVE_RANGE = (-0.1, 1.1)
DIVE_GRACE_MAX_MS = 2000  # upper bound for the optional diveGraceMs setting
PATROL_X = (0.2, 0.8)
PATROL_Y = (0.3, 0.36)  # small hops

# The keeper as drawn by the client, in scene units (the goal mouth is GOAL_W x GOAL_H, y down)
# around the hands point: circles (x, y, r), rectangles (x1, y1, x2, y2), arms (x1, y1, x2, y2, r).
GOAL_W, GOAL_H = 280, 180
BALL_R_AT_GOAL = 8
KEEPER_CIRCLES = ((0, -58, 13), (-28, 0, 7), (28, 0, 7))
KEEPER_RECTS = ((-16, -44, 16, 12), (-15, 8, 15, 54))
KEEPER_ARMS = ((-14, -36, -28, 0, 4), (14, -36, 28, 0, 4))


@dataclass
class PenaltyState:
    a: str
    b: str
    first: str
    kicks_per_player: int
    keeper_speed: str
    rng: random.Random
    scores: dict[str, int]
    taken: dict[str, int]
    kicks: list[dict[str, Any]] = field(default_factory=list)  # resolved kicks, in order
    phase: str = "aiming"  # aiming | flight | result | over
    deadline: float | None = None  # aiming: the shooter's deadline
    path: list[dict[str, float]] = field(default_factory=list)  # aiming: the keeper's patrol
    shot: dict[str, Any] | None = None  # flight and result: launchAt, arriveAt, to, power, spot
    dive: dict[str, float] | None = None  # the accepted dive: x, y, receivedAt
    outcome: str | None = None  # result phase only
    result_until: float | None = None
    decided: str | None = None  # the winner, declared when the result phase ends
    winner: str | None = None
    grace_ms: float = PENALTY_DIVE_GRACE_MS  # how long after arriveAt a dive still counts


def flight_ms(power: float) -> float:
    """Linear from PENALTY_FLIGHT_MS_MAX at power 0 to PENALTY_FLIGHT_MS_MIN at power 1."""
    return PENALTY_FLIGHT_MS_MAX - (PENALTY_FLIGHT_MS_MAX - PENALTY_FLIGHT_MS_MIN) * power


def wobble_sd(power: float) -> float:
    """Spread of the real aim around the aim, per axis."""
    wild = max(0.0, power - PENALTY_POWER_SWEET_MAX) / (1 - PENALTY_POWER_SWEET_MAX)
    return PENALTY_WOBBLE_BASE + PENALTY_WOBBLE_WILD * wild


def real_aim(aim: dict[str, float], power: float, rng: random.Random) -> dict[str, float]:
    """Where the ball actually goes. A fizzled shot keeps its aim (it stops short anyway)."""
    if power < PENALTY_POWER_FIZZLE:
        return {"x": aim["x"], "y": max(0.0, aim["y"])}
    sd = wobble_sd(power)
    return {"x": rng.gauss(aim["x"], sd), "y": max(0.0, rng.gauss(aim["y"], sd))}


def off_target(to: dict[str, float]) -> str | None:
    """'wide', 'over' or 'post' for a ball that misses the goal mouth, else None."""
    x, y, m = to["x"], to["y"], PENALTY_POST_MARGIN
    if x < -m or x > 1 + m:
        return "wide"
    if y > 1 + m:
        return "over"
    if x < 0 or x > 1 or y > 1:
        return "post"
    return None


def reach(power: float) -> float:
    """How far (in goal widths) a diving keeper's hands reach; more against slow shots."""
    return PENALTY_SAVE_RADIUS + PENALTY_SLOW_BONUS * (1 - power)


def dive_angle(spot: dict[str, float], dive: dict[str, float]) -> float:
    """The keeper's lean (degrees, clockwise on screen) diving from `spot` to `dive`."""
    return min(80.0, max(-80.0, (dive["x"] - spot["x"]) * 160))


def _segment_distance(px: float, py: float, x1, y1, x2, y2) -> float:
    vx, vy = x2 - x1, y2 - y1
    t = max(0.0, min(1.0, ((px - x1) * vx + (py - y1) * vy) / (vx * vx + vy * vy)))
    return math.hypot(px - x1 - t * vx, py - y1 - t * vy)


def hits_keeper(
    to: dict[str, float], spot: dict[str, float], dive: dict[str, float] | None
) -> bool:
    """Whether the ball touches the keeper's body standing at `spot` or diving to `dive`."""
    hands = dive if dive is not None else spot
    angle = math.radians(dive_angle(spot, dive) if dive is not None else 0.0)
    dx, dy = (to["x"] - hands["x"]) * GOAL_W, (hands["y"] - to["y"]) * GOAL_H
    # Into the keeper's own frame: undo the lean around the hands.
    x = dx * math.cos(angle) + dy * math.sin(angle)
    y = -dx * math.sin(angle) + dy * math.cos(angle)
    r = BALL_R_AT_GOAL
    if any(math.hypot(x - cx, y - cy) <= cr + r for cx, cy, cr in KEEPER_CIRCLES):
        return True
    if any(x1 - r <= x <= x2 + r and y1 - r <= y <= y2 + r for x1, y1, x2, y2 in KEEPER_RECTS):
        return True
    return any(_segment_distance(x, y, *arm[:4]) <= arm[4] + r for arm in KEEPER_ARMS)


def resolve_kick(
    to: dict[str, float], power: float, spot: dict[str, float], dive: dict[str, float] | None
) -> str:
    """The outcome of a ball heading for `to` against a keeper at `spot` (None dive: no dive)."""
    if power < PENALTY_POWER_FIZZLE:
        return "fizzled"
    miss = off_target(to)
    if miss is not None:
        return miss
    if hits_keeper(to, spot, dive):
        return "saved"
    if dive is not None:
        gap = math.hypot(to["x"] - dive["x"], (to["y"] - dive["y"]) * GOAL_H / GOAL_W)
        if gap <= reach(power):
            return "saved"
    return "goal"


def keeper_path(start: float, speed: str, rng: random.Random) -> list[dict[str, float]]:
    """The keeper's patrol for one aiming phase: from home, pause, move to a random point, ...

    Keyframes {at, x, y}; the keeper moves in a straight line between them.
    """
    pace, pause = PENALTY_KEEPER_SPEED[speed], PENALTY_KEEPER_PAUSE_MS[speed]
    path = [{"at": start, **KEEPER_HOME}]
    while path[-1]["at"] < start + PENALTY_AIM_MS:
        last = path[-1]
        path.append({**last, "at": last["at"] + pause})
        x, y = rng.uniform(*PATROL_X), rng.uniform(*PATROL_Y)
        widths = math.hypot(x - last["x"], (y - last["y"]) * GOAL_H / GOAL_W)
        path.append({"at": path[-1]["at"] + max(1.0, widths / pace * 1000), "x": x, "y": y})
    return path


def keeper_at(path: list[dict[str, float]], now: float) -> dict[str, float]:
    """Where the patrolling keeper is at `now` (home without a path)."""
    if not path:
        return dict(KEEPER_HOME)
    for a, b in zip(path, path[1:], strict=False):
        if now < b["at"]:
            k = max(0.0, (now - a["at"]) / (b["at"] - a["at"]))
            return {"x": a["x"] + (b["x"] - a["x"]) * k, "y": a["y"] + (b["y"] - a["y"]) * k}
    return {"x": path[-1]["x"], "y": path[-1]["y"]}


def _number(value: Any, low: float, high: float, what: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise GameError("INVALID_ACTION", f"Bad {what}.")
    return float(value)


def _clamp(value: Any, low: float, high: float, what: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise GameError("INVALID_ACTION", f"Bad {what}.")
    return min(high, max(low, float(value)))


class PenaltyKickEngine(MatchEngine):
    def init(self, player_a, player_b, settings, rng, first_mover) -> PenaltyState:
        players = [player_a, player_b]
        return PenaltyState(
            player_a,
            player_b,
            first_mover,
            settings["kicksPerPlayer"],
            settings["keeperSpeed"],
            rng,
            dict.fromkeys(players, 0),
            dict.fromkeys(players, 0),
            grace_ms=settings.get("diveGraceMs", PENALTY_DIVE_GRACE_MS),
        )

    def shooter(self, state: PenaltyState) -> str:
        """The shooter of the kick in play (in the result phase: of the kick just taken)."""
        done = len(state.kicks) - (1 if state.phase == "result" else 0)
        second = state.b if state.first == state.a else state.a
        return state.first if done % 2 == 0 else second

    def keeper(self, state: PenaltyState) -> str:
        return state.b if self.shooter(state) == state.a else state.a

    def apply(self, state: PenaltyState, player_id, action, now) -> tuple[Any, list[GameEvent]]:
        if state.phase == "over":
            raise GameError("INVALID_ACTION", "The shootout is over.")
        if player_id not in state.scores:
            raise GameError("NOT_YOUR_TURN", "You are not in this shootout.")
        kind = action.get("type")
        if player_id == self.shooter(state):
            if kind != "shoot":
                raise GameError("INVALID_ACTION", "You are shooting.")
            if state.phase != "aiming":
                raise GameError("INVALID_ACTION", "The ball is already kicked.")
            return state, [self._shoot(state, action, now)]
        if kind != "dive":
            raise GameError("INVALID_ACTION", "You are the keeper.")
        if state.phase == "aiming":
            raise GameError("INVALID_ACTION", "Wait for the kick.")
        x = _clamp(action.get("x"), *DIVE_RANGE, "dive")
        y = _clamp(action.get("y"), *DIVE_RANGE, "dive")
        assert state.shot is not None
        late = state.phase != "flight" or now > state.shot["arriveAt"] + state.grace_ms
        if state.dive is None and not late:
            state.dive = {"x": x, "y": y, "receivedAt": now}
        return state, []  # a second or late dive is ignored

    def _shoot(self, state: PenaltyState, action: dict[str, Any], now: float) -> GameEvent:
        aim = action.get("aim")
        if not isinstance(aim, dict):
            raise GameError("INVALID_ACTION", "Bad aim.")
        target = {
            "x": _number(aim.get("x"), *AIM_RANGE, "aim"),
            "y": _number(aim.get("y"), *AIM_RANGE, "aim"),
        }
        power = _number(action.get("power"), 0, 1, "power")
        state.shot = {
            "launchAt": now,
            "arriveAt": now + flight_ms(power),
            "to": real_aim(target, power, state.rng),
            "power": power,
            "keeperSpot": keeper_at(state.path, now),
        }
        state.phase, state.deadline, state.dive, state.path = "flight", None, None, []
        return {
            "kind": "penalty_launch",
            "data": {"kick": len(state.kicks) + 1, "shooter": self.shooter(state)},
        }

    def _resolve(self, state: PenaltyState, now: float) -> GameEvent:
        shot = state.shot
        assert shot is not None
        shooter, keeper = self.shooter(state), self.keeper(state)
        dive = None if state.dive is None else {"x": state.dive["x"], "y": state.dive["y"]}
        outcome = resolve_kick(shot["to"], shot["power"], shot["keeperSpot"], dive)
        kick = {
            "kick": len(state.kicks) + 1,
            "shooter": shooter,
            "keeper": keeper,
            "to": dict(shot["to"]),
            "power": shot["power"],
            "keeperSpot": dict(shot["keeperSpot"]),
            "dive": dive,
            "outcome": outcome,
        }
        state.kicks.append(kick)
        state.taken[shooter] += 1
        if outcome == "goal":
            state.scores[shooter] += 1
        state.phase, state.outcome = "result", outcome
        state.result_until = now + PENALTY_RESULT_MS
        state.decided = self._decided(state)
        return {"kind": "penalty_result", "data": {**kick, "scores": dict(state.scores)}}

    @staticmethod
    def _decided(state: PenaltyState) -> str | None:
        """The winner once the other side cannot catch up within the kicks they are owed.

        Each player is owed `kicksPerPlayer` kicks, then one more per sudden-death pair.
        """
        owed = max(state.kicks_per_player, (len(state.kicks) + 1) // 2)
        sa, sb = state.scores[state.a], state.scores[state.b]
        if sa > sb + owed - state.taken[state.b]:
            return state.a
        if sb > sa + owed - state.taken[state.a]:
            return state.b
        return None

    def tick(self, state: PenaltyState, now) -> tuple[Any, list[GameEvent]]:
        events: list[GameEvent] = []
        if state.phase == "aiming" and state.deadline is None:
            self._aim(state, now)
        elif state.phase == "flight":
            assert state.shot is not None
            if now >= state.shot["arriveAt"] + state.grace_ms:
                events.append(self._resolve(state, now))
        elif state.phase == "result" and state.result_until is not None:
            if now >= state.result_until:
                state.shot = state.dive = state.outcome = state.result_until = None
                if state.decided is not None:
                    state.phase, state.winner = "over", state.decided
                else:
                    state.phase = "aiming"
                    self._aim(state, now)
        return state, events

    @staticmethod
    def _aim(state: PenaltyState, now: float) -> None:
        state.deadline = now + PENALTY_AIM_MS
        state.path = keeper_path(now, state.keeper_speed, state.rng)

    def awaiting(self, state: PenaltyState) -> list[str]:
        return [self.shooter(state)] if state.phase == "aiming" else []

    def random_action(self, state: PenaltyState, player_id, rng: random.Random) -> dict[str, Any]:
        """A mild shot somewhere inside the goal (the keeper never owes an action)."""
        aim = {"x": rng.uniform(0.15, 0.85), "y": rng.uniform(0.1, 0.8)}
        return {"type": "shoot", "aim": aim, "power": 0.5}

    def public_view(self, state: PenaltyState) -> dict[str, Any]:
        live = state.phase != "over"
        shot = state.shot
        flight = None
        if shot is not None:
            flight = {
                "launchAt": shot["launchAt"],
                "arriveAt": shot["arriveAt"],
                "graceMs": state.grace_ms,
                "ball": {"from": dict(BALL_FROM), "to": dict(shot["to"]), "power": shot["power"]},
                "keeperSpot": dict(shot["keeperSpot"]),
                "dive": None if state.dive is None else dict(state.dive),
            }
        return {
            "kicksPerPlayer": state.kicks_per_player,
            "keeperSpeed": state.keeper_speed,
            "firstMover": state.first,
            "phase": state.phase,
            "shooter": self.shooter(state) if live else None,
            "keeper": self.keeper(state) if live else None,
            "kickNo": len(state.kicks) + (0 if state.phase in ("result", "over") else 1),
            "round": (len(state.kicks) - (1 if state.phase == "result" else 0)) // 2 + 1,
            "suddenDeath": len(state.kicks) >= 2 * state.kicks_per_player,
            "scores": dict(state.scores),
            "kicks": [
                {**k, "to": dict(k["to"]), "keeperSpot": dict(k["keeperSpot"])} for k in state.kicks
            ],
            "lastKick": dict(state.kicks[-1]) if state.kicks else None,
            "turnDeadline": state.deadline if state.phase == "aiming" else None,
            "keeperPath": [dict(p) for p in state.path] if state.phase == "aiming" else None,
            "flight": flight,
            "outcome": state.outcome,
            "resultUntil": state.result_until,
            "winner": state.winner,
        }

    def view_for(self, state: PenaltyState, player_id) -> dict[str, Any]:
        view = self.public_view(state)
        role = "shooter" if view["shooter"] == player_id else "keeper" if view["keeper"] else None
        return {**view, "yourRole": role}

    def status(self, state: PenaltyState) -> Outcome:
        return ("winner", state.winner) if state.winner is not None else ("ongoing", None)

    def next_deadline(self, state: PenaltyState) -> float | None:
        if state.phase == "aiming":
            return state.deadline
        if state.phase == "flight" and state.shot is not None:
            return state.shot["arriveAt"] + state.grace_ms
        if state.phase == "result":
            return state.result_until
        return None


class PenaltyKick(SeriesGame):
    id = "penalty_kick"
    name = "Penalty Kick"
    default_settings: dict[str, Any] = {"kicksPerPlayer": 5, "keeperSpeed": "normal"}
    engine = PenaltyKickEngine()

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        grace = settings.get("diveGraceMs")  # optional; not part of the default settings
        settings = {k: v for k, v in settings.items() if k != "diveGraceMs"}
        merged = super().validate_settings(settings)
        if grace is not None:
            if type(grace) is not int or not 0 <= grace <= DIVE_GRACE_MAX_MS:
                raise GameError("INVALID_ACTION", "diveGraceMs is out of range.")
            merged["diveGraceMs"] = grace
        if type(merged["kicksPerPlayer"]) is not int or merged["kicksPerPlayer"] not in (3, 5):
            raise GameError("INVALID_ACTION", "kicksPerPlayer must be 3 or 5.")
        if merged["keeperSpeed"] not in KEEPER_SPEEDS:
            raise GameError("INVALID_ACTION", "keeperSpeed must be easy, normal or hard.")
        return merged

    def best_of(self, settings: dict[str, Any]) -> int:
        return 1  # a shootout is one game per match
