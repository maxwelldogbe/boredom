"""Rock-Paper-Scissors: a duel, or a knockout bracket for 3+ players (plan section 7).

Each match is best of `bestOf`; ties replay. Matches of one bracket round run in parallel,
each with its own pick timer and reveal pause. Odd player counts give a bye to a random
player, preferring players who have not had one yet. Placement is by the bracket round a
player lost in (champion 1, runner-up 2, losing semifinalists tied 3rd, ...); the display
score is matches won.

A forfeiting player loses their current match and the opponent advances. A player whose
match is already decided (a bye, or a won match) simply leaves the bracket before the
next pairing.
"""

import random
from dataclasses import dataclass, field
from typing import Any, Literal

from games.base import (
    ForfeitReason,
    GameError,
    GameEvent,
    GameModule,
    GameResult,
    competition_placements,
)
from games.constants import RPS_PICK_TIMEOUT_MS, RPS_REVEAL_MS

CHOICES = ("rock", "paper", "scissors")
BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}

MatchPhase = Literal["picking", "reveal", "over"]


@dataclass
class Match:
    """One pairing. `b` is None for a bye. `picks` holds the current, still secret round."""

    a: str
    b: str | None
    scores: dict[str, int]
    picks: dict[str, str | None]
    phase: MatchPhase = "picking"
    round: int = 1
    deadline: float | None = None
    winner: str | None = None
    last_reveal: dict[str, Any] | None = None

    def players(self) -> list[str]:
        return [self.a] if self.b is None else [self.a, self.b]


@dataclass
class RpsState:
    best_of: int
    mode: str
    rng: random.Random
    alive: list[str]
    bracket_round: int = 0
    matches: list[Match] = field(default_factory=list)
    out_round: dict[str, int] = field(default_factory=dict)  # player -> bracket round lost
    champion: str | None = None
    all_players: list[str] = field(default_factory=list)
    byes: list[str] = field(default_factory=list)  # players who had a bye, in order
    match_wins: dict[str, int] = field(default_factory=dict)  # byes don't count


class RockPaperScissors(GameModule):
    id = "rps"
    name = "Rock-Paper-Scissors"
    min_players = 2
    max_players = 10
    default_settings: dict[str, Any] = {"bestOf": 3, "mode": "duel"}

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = {**self.default_settings, **settings}
        if set(merged) != set(self.default_settings):
            raise GameError("INVALID_ACTION", "Unknown setting.")
        if type(merged["bestOf"]) is not int or merged["bestOf"] not in (3, 5):
            raise GameError("INVALID_ACTION", "bestOf must be 3 or 5.")
        if merged["mode"] not in ("duel", "bracket"):
            raise GameError("INVALID_ACTION", "mode must be duel or bracket.")
        return merged

    def init(self, players: list[str], settings: dict[str, Any], rng: random.Random, now: float):
        mode = "duel" if len(players) == 2 else settings["mode"]
        if mode == "duel" and len(players) != 2:
            raise GameError("INVALID_ACTION", "Duel needs exactly 2 players. Choose bracket.")
        state = RpsState(settings["bestOf"], mode, rng, list(players), all_players=list(players))
        state.match_wins = dict.fromkeys(players, 0)
        self._start_bracket_round(state, now, [])
        return state

    # ----- actions and timers --------------------------------------------------------------

    def handle_action(self, state: RpsState, player_id, action, now) -> tuple[Any, list[GameEvent]]:
        if action.get("type") != "pick":
            raise GameError("INVALID_ACTION", "Unknown action.")
        choice = action.get("choice")
        if choice not in CHOICES:
            raise GameError("INVALID_ACTION", "Pick rock, paper or scissors.")
        match = self._match_of(state, player_id)
        if match is None or match.phase == "over" or match.b is None:
            raise GameError("NOT_YOUR_TURN", "You are not in a match right now.")
        if match.phase != "picking":
            raise GameError("NOT_YOUR_TURN", "Wait for the next round.")
        if match.picks[player_id] is not None:
            raise GameError("INVALID_ACTION", "You already picked.")
        match.picks[player_id] = choice
        events: list[GameEvent] = []
        if all(match.picks.values()):
            self._resolve(state, match, now, events)
        return state, events

    def tick(self, state: RpsState, now) -> tuple[Any, list[GameEvent]]:
        events: list[GameEvent] = []
        if state.champion is not None:
            return state, events
        for match in state.matches:
            if match.phase == "over":
                continue
            if match.deadline is not None and now >= match.deadline:
                if match.phase == "picking":
                    self._resolve(state, match, now, events)
                elif match.winner is not None:
                    self._end_match(state, match, match.winner, "score", events)
                else:
                    match.phase, match.round = "picking", match.round + 1
                    match.picks = dict.fromkeys(match.players())
                    match.deadline = now + RPS_PICK_TIMEOUT_MS
        if all(m.phase == "over" for m in state.matches):
            self._start_bracket_round(state, now, events)
        return state, events

    def forfeit(
        self, state: RpsState, player_id: str, now: float, reason: ForfeitReason
    ) -> tuple[Any, list[GameEvent]]:
        events: list[GameEvent] = []
        if state.champion is not None or player_id not in state.alive:
            return state, events
        match = self._match_of(state, player_id)
        if match is not None and match.phase != "over" and match.b is not None:
            opponent = match.b if player_id == match.a else match.a
            self._end_match(state, match, opponent, "forfeit", events)
        else:  # bye or already through: out before the next pairing
            state.alive.remove(player_id)
            state.out_round[player_id] = state.bracket_round
        if all(m.phase == "over" for m in state.matches):
            self._start_bracket_round(state, now, events)
        return state, events

    def next_deadline(self, state: RpsState) -> float | None:
        times = [m.deadline for m in state.matches if m.phase != "over" and m.deadline]
        return min(times) if times and state.champion is None else None

    # ----- rules ---------------------------------------------------------------------------

    def _start_bracket_round(self, state: RpsState, now: float, events: list[GameEvent]) -> None:
        if len(state.alive) == 1:
            state.champion = state.alive[0]
            return
        state.bracket_round += 1
        order = list(state.alive)
        state.rng.shuffle(order)
        if len(order) % 2:
            fresh = [p for p in order if p not in state.byes]
            bye = state.rng.choice(fresh or order)
            order.remove(bye)
            order.append(bye)
            state.byes.append(bye)
        state.matches = []
        for i in range(0, len(order), 2):
            a, b = order[i], order[i + 1] if i + 1 < len(order) else None
            players = [a] if b is None else [a, b]
            match = Match(a, b, dict.fromkeys(players, 0), dict.fromkeys(players))
            match.deadline = now + RPS_PICK_TIMEOUT_MS
            state.matches.append(match)
            if b is None:
                match.phase, match.winner, match.deadline = "over", a, None
                events.append(
                    {
                        "kind": "matchOver",
                        "data": {
                            "matchIndex": len(state.matches) - 1,
                            "winnerId": a,
                            "loserId": None,
                            "reason": "bye",
                        },
                    }
                )
        events.append(
            {
                "kind": "bracketRound",
                "data": {
                    "bracketRound": state.bracket_round,
                    "pairs": [[m.a, m.b] for m in state.matches],
                },
            }
        )

    def _resolve(self, state: RpsState, match: Match, now: float, events: list[GameEvent]) -> None:
        """Reveal the current round: a non-picker loses it; equal picks (or none) replay."""
        assert match.b is not None
        pa, pb = match.picks[match.a], match.picks[match.b]
        if pa and pb:
            winner = None if pa == pb else (match.a if BEATS[pa] == pb else match.b)
        else:
            winner = match.a if pa else match.b if pb else None
        if winner is not None:
            match.scores[winner] += 1
        needed = state.best_of // 2 + 1
        if winner is not None and match.scores[winner] >= needed:
            match.winner = winner
        match.last_reveal = {
            "round": match.round,
            "picks": dict(match.picks),
            "roundWinner": winner,
        }
        match.phase, match.deadline = "reveal", now + RPS_REVEAL_MS
        index = state.matches.index(match)
        events.append(
            {
                "kind": "reveal",
                "data": {"matchIndex": index, **match.last_reveal, "scores": dict(match.scores)},
            }
        )

    def _end_match(
        self, state: RpsState, match: Match, winner: str, reason: str, events: list[GameEvent]
    ) -> None:
        loser = match.b if winner == match.a else match.a
        match.phase, match.winner, match.deadline = "over", winner, None
        match.picks = dict.fromkeys(match.players())
        if loser is not None:
            state.match_wins[winner] += 1
            state.alive.remove(loser)
            state.out_round[loser] = state.bracket_round
        events.append(
            {
                "kind": "matchOver",
                "data": {
                    "matchIndex": state.matches.index(match),
                    "winnerId": winner,
                    "loserId": loser,
                    "reason": reason,
                },
            }
        )

    @staticmethod
    def _match_of(state: RpsState, player_id: str) -> Match | None:
        return next((m for m in state.matches if player_id in m.players()), None)

    # ----- views and results -----------------------------------------------------------------

    def get_view(self, state: RpsState, player_id: str) -> dict[str, Any]:
        mine = self._match_of(state, player_id)
        if state.champion is not None:
            phase = "done"
        elif mine is None or mine.phase == "over":
            phase = "matchOver"
        else:
            phase = mine.phase
        return {
            "phase": phase,
            "mode": state.mode,
            "bestOf": state.best_of,
            "bracketRound": state.bracket_round,
            "myMatch": state.matches.index(mine) if mine is not None else None,
            "myPick": mine.picks.get(player_id) if mine is not None else None,
            "matches": [self._match_public(m) for m in state.matches],
            "alive": list(state.alive),
            "eliminated": [p for p in state.all_players if p in state.out_round],
            "champion": state.champion,
        }

    @staticmethod
    def _match_public(match: Match) -> dict[str, Any]:
        """Public match info: never the current round's picks, only `hasPicked`."""
        return {
            "a": match.a,
            "b": match.b,
            "phase": match.phase,
            "round": match.round,
            "scores": dict(match.scores),
            "hasPicked": {p: match.picks[p] is not None for p in match.players()},
            "deadline": match.deadline,
            "winner": match.winner,
            "lastReveal": match.last_reveal,
        }

    def is_over(self, state: RpsState) -> bool:
        return state.champion is not None

    def get_results(self, state: RpsState) -> list[GameResult]:
        placements = rps_placements(state)
        return [
            {"player_id": pid, "placement": placements[pid], "score": state.match_wins[pid]}
            for pid in sorted(state.all_players, key=lambda p: placements[p])
        ]


def rps_placements(state: RpsState) -> dict[str, int]:
    """By the bracket round a player lost in; later is better, the champion never lost."""
    last = state.bracket_round + 1
    depth = {p: state.out_round.get(p, last) for p in state.all_players}
    return competition_placements(depth)
