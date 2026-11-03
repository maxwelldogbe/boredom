"""Turns any two-player MatchEngine into a game module: best-of matches in a knockout bracket.

The bracket works like rps: each round pairs the players still in at random (an odd count
gives a bye, preferring players who have not had one), matches of a round run at the same
time and winners advance. Placement is by the bracket round a player lost in (champion 1,
runner-up 2, losing semifinalists tied 3rd, ...); the display score is matches won.

A match is best of `bestOf` games (first to the majority). The first mover alternates every
game, drawn games included; a draw does not count and the game is replayed. After
MATCH_MAX_DRAWS draws the match goes to the rng and is flagged `coinFlip`.

AFK: a timed-out move is replaced by a random legal one; MATCH_AFK_TIMEOUTS_TO_FORFEIT
timeouts in a row by one player lose them the match.

Players not in a live match (a bye, a won match waiting for the round, or knocked out) are
spectators: they see the public view of one live match and may switch with `watch`.
"""

import random
from dataclasses import dataclass, field
from typing import Any, ClassVar

from games.base import (
    ForfeitReason,
    GameError,
    GameEvent,
    GameModule,
    GameResult,
    competition_placements,
)
from games.constants import MATCH_AFK_TIMEOUTS_TO_FORFEIT, MATCH_MAX_DRAWS
from games.match_engine import MatchEngine

BEST_OF = (1, 3, 5)


@dataclass
class SeriesMatch:
    """One pairing. `b` is None for a bye. `game` is the engine state of the current game."""

    id: str
    a: str
    b: str | None
    wins: dict[str, int]
    timeouts: dict[str, int]  # timeouts in a row
    game: Any = None
    game_no: int = 0  # games started, draws included
    draws: int = 0
    winner: str | None = None
    reason: str | None = None  # bye | score | forfeit | afk | coinFlip
    coin_flip: bool = False
    last_game: dict[str, Any] | None = None

    def players(self) -> list[str]:
        return [self.a] if self.b is None else [self.a, self.b]

    def opponent(self, player_id: str) -> str | None:
        return self.b if player_id == self.a else self.a


@dataclass
class SeriesState:
    settings: dict[str, Any]
    best_of: int
    rng: random.Random
    alive: list[str]
    all_players: list[str]
    bracket_round: int = 0
    matches: list[SeriesMatch] = field(default_factory=list)
    out_round: dict[str, int] = field(default_factory=dict)  # player -> bracket round lost
    champion: str | None = None
    byes: list[str] = field(default_factory=list)
    match_wins: dict[str, int] = field(default_factory=dict)  # byes don't count
    watching: dict[str, str] = field(default_factory=dict)  # spectator -> match id


class SeriesGame(GameModule):
    """Subclasses set `engine` and the GameModule class attributes."""

    engine: ClassVar[MatchEngine]
    min_players = 2
    max_players = 10

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = {**self.default_settings, **settings}
        if set(merged) != set(self.default_settings):
            raise GameError("INVALID_ACTION", "Unknown setting.")
        if "bestOf" in merged and (
            type(merged["bestOf"]) is not int or merged["bestOf"] not in BEST_OF
        ):
            raise GameError("INVALID_ACTION", "bestOf must be 1, 3 or 5.")
        return merged

    def best_of(self, settings: dict[str, Any]) -> int:
        """Games per match. Override for games without a `bestOf` setting."""
        return settings["bestOf"]

    def init(self, players: list[str], settings: dict[str, Any], rng: random.Random, now: float):
        if not self.min_players <= len(players) <= self.max_players:
            raise GameError("INVALID_ACTION", f"{self.name} needs 2 to 10 players.")
        state = SeriesState(
            dict(settings), self.best_of(settings), rng, list(players), list(players)
        )
        state.match_wins = dict.fromkeys(players, 0)
        self._start_round(state, now, [])
        return state

    # ----- actions and timers --------------------------------------------------------------

    def handle_action(
        self, state: SeriesState, player_id, action, now
    ) -> tuple[Any, list[GameEvent]]:
        if action.get("type") == "watch":
            self._watch(state, player_id, action.get("matchId"))
            return state, []
        match = self._live_match_of(state, player_id)
        if match is None:
            raise GameError("NOT_YOUR_TURN", "You are not in a match right now.")
        match.game, engine_events = self.engine.apply(match.game, player_id, action, now)
        match.timeouts[player_id] = 0
        events = self._tag(match, engine_events)
        self._after_move(state, match, now, events)
        self._maybe_next_round(state, now, events)
        return state, events

    def tick(self, state: SeriesState, now) -> tuple[Any, list[GameEvent]]:
        events: list[GameEvent] = []
        if state.champion is not None:
            return state, events
        for match in self._live_matches(state):
            deadline = self.engine.next_deadline(match.game)
            if deadline is None or now < deadline:
                continue
            owed = self.engine.awaiting(match.game)
            if not owed:
                match.game, engine_events = self.engine.tick(match.game, now)
                events.extend(self._tag(match, engine_events))
            for pid in owed:
                if pid not in self.engine.awaiting(match.game):
                    continue
                action = self.engine.random_action(match.game, pid, state.rng)
                match.game, engine_events = self.engine.apply(match.game, pid, action, now)
                match.timeouts[pid] += 1
                events.append({"kind": "autoMove", "data": {"matchId": match.id, "playerId": pid}})
                events.extend(self._tag(match, engine_events))
                if match.timeouts[pid] >= MATCH_AFK_TIMEOUTS_TO_FORFEIT:
                    self._end_match(state, match, match.opponent(pid), "afk", events)
                    break
            if match.winner is None:
                self._after_move(state, match, now, events)
        self._maybe_next_round(state, now, events)
        return state, events

    def forfeit(
        self, state: SeriesState, player_id: str, now: float, reason: ForfeitReason
    ) -> tuple[Any, list[GameEvent]]:
        events: list[GameEvent] = []
        state.watching.pop(player_id, None)
        if state.champion is not None or player_id not in state.alive:
            return state, events
        match = self._live_match_of(state, player_id)
        if match is not None:
            self._end_match(state, match, match.opponent(player_id), "forfeit", events)
        else:  # bye or already through: out before the next pairing
            state.alive.remove(player_id)
            state.out_round[player_id] = state.bracket_round
        self._maybe_next_round(state, now, events)
        return state, events

    def next_deadline(self, state: SeriesState) -> float | None:
        if state.champion is not None:
            return None
        times = [self.engine.next_deadline(m.game) for m in self._live_matches(state)]
        times = [t for t in times if t is not None]
        return min(times) if times else None

    # ----- rules ---------------------------------------------------------------------------

    def _start_round(self, state: SeriesState, now: float, events: list[GameEvent]) -> None:
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
            match = SeriesMatch(
                f"r{state.bracket_round}m{i // 2 + 1}",
                a,
                b,
                dict.fromkeys(players, 0),
                dict.fromkeys(players, 0),
            )
            state.matches.append(match)
            if b is None:
                match.winner, match.reason = a, "bye"
                events.append(self._match_over_event(match, None))
            else:
                self._next_game(state, match, now)
        events.append(
            {
                "kind": "bracketRound",
                "data": {
                    "bracketRound": state.bracket_round,
                    "pairs": [[m.a, m.b] for m in state.matches],
                },
            }
        )

    def _next_game(self, state: SeriesState, match: SeriesMatch, now: float) -> None:
        """Start the next game of a match; the first mover alternates, seat 1 opening game 1."""
        assert match.b is not None
        match.game_no += 1
        first = match.a if match.game_no % 2 else match.b
        match.game = self.engine.init(match.a, match.b, state.settings, state.rng, first)
        match.game, _ = self.engine.tick(match.game, now)

    def _after_move(
        self, state: SeriesState, match: SeriesMatch, now: float, events: list[GameEvent]
    ) -> None:
        """Score a finished game: a win counts, a draw replays (or goes to the coin)."""
        result, winner = self.engine.status(match.game)
        if result == "ongoing":
            return
        match.last_game = {
            "gameNo": match.game_no,
            "result": result,
            "winner": winner,
            "game": self.engine.public_view(match.game),
        }
        events.append({"kind": "gameEnd", "data": {"matchId": match.id, **match.last_game}})
        needed = state.best_of // 2 + 1
        if winner is not None:
            match.wins[winner] += 1
            if match.wins[winner] >= needed:
                self._end_match(state, match, winner, "score", events)
                return
        else:
            match.draws += 1
            if match.draws >= MATCH_MAX_DRAWS:
                match.coin_flip = True
                pick = state.rng.choice(match.players())
                self._end_match(state, match, pick, "coinFlip", events)
                return
        self._next_game(state, match, now)

    def _end_match(
        self,
        state: SeriesState,
        match: SeriesMatch,
        winner: str | None,
        reason: str,
        events: list[GameEvent],
    ) -> None:
        assert winner is not None
        loser = match.opponent(winner)
        match.winner, match.reason = winner, reason
        if loser is not None:
            state.match_wins[winner] += 1
            state.alive.remove(loser)
            state.out_round[loser] = state.bracket_round
        events.append(self._match_over_event(match, loser))

    def _maybe_next_round(self, state: SeriesState, now: float, events: list[GameEvent]) -> None:
        if state.champion is None and all(m.winner is not None for m in state.matches):
            self._start_round(state, now, events)

    def _watch(self, state: SeriesState, player_id: str, match_id: Any) -> None:
        if self._live_match_of(state, player_id) is not None:
            raise GameError("INVALID_ACTION", "Only spectators can switch matches.")
        if match_id not in [m.id for m in self._live_matches(state)]:
            raise GameError("INVALID_ACTION", "That match is not being played.")
        state.watching[player_id] = match_id

    @staticmethod
    def _match_over_event(match: SeriesMatch, loser: str | None) -> GameEvent:
        return {
            "kind": "matchOver",
            "data": {
                "matchId": match.id,
                "winnerId": match.winner,
                "loserId": loser,
                "reason": match.reason,
                "coinFlip": match.coin_flip,
            },
        }

    @staticmethod
    def _tag(match: SeriesMatch, events: list[GameEvent]) -> list[GameEvent]:
        return [{"kind": e["kind"], "data": {"matchId": match.id, **e["data"]}} for e in events]

    @staticmethod
    def _live_matches(state: SeriesState) -> list[SeriesMatch]:
        return [m for m in state.matches if m.winner is None]

    def _live_match_of(self, state: SeriesState, player_id: str) -> SeriesMatch | None:
        return next((m for m in self._live_matches(state) if player_id in m.players()), None)

    # ----- views and results ---------------------------------------------------------------

    def get_view(self, state: SeriesState, player_id: str) -> dict[str, Any]:
        mine = self._live_match_of(state, player_id)
        live = self._live_matches(state)
        if state.champion is not None:
            phase = "done"
        elif mine is not None:
            phase = "playing"
        elif player_id in state.alive:
            phase = "waiting"
        else:
            phase = "out"
        if mine is not None:
            shown: SeriesMatch | None = mine
            game = self.engine.view_for(mine.game, player_id)
        else:
            wanted = state.watching.get(player_id)
            own = next((m for m in state.matches if player_id in m.players()), None)
            shown = next((m for m in live if m.id == wanted), None) or (
                live[0] if live else own if own is not None and own.b is not None else None
            )
            game = self.engine.public_view(shown.game) if shown is not None else None
        return {
            "phase": phase,
            "role": "player" if mine is not None else "spectator",
            "bestOf": state.best_of,
            "winsNeeded": state.best_of // 2 + 1,
            "bracketRound": state.bracket_round,
            "matches": [self._match_public(m) for m in state.matches],
            "liveMatches": [m.id for m in live],
            "match": None if shown is None else {**self._match_public(shown), "game": game},
            "watching": shown.id if mine is None and shown is not None else None,
            "alive": list(state.alive),
            "eliminated": [p for p in state.all_players if p in state.out_round],
            "champion": state.champion,
        }

    @staticmethod
    def _match_public(match: SeriesMatch) -> dict[str, Any]:
        return {
            "id": match.id,
            "a": match.a,
            "b": match.b,
            "phase": "playing" if match.winner is None else "over",
            "wins": dict(match.wins),
            "gameNo": match.game_no,
            "draws": match.draws,
            "winner": match.winner,
            "reason": match.reason,
            "coinFlip": match.coin_flip,
            "lastGame": match.last_game,
        }

    def is_over(self, state: SeriesState) -> bool:
        return state.champion is not None

    def get_results(self, state: SeriesState) -> list[GameResult]:
        last = state.bracket_round + 1
        depth = {p: state.out_round.get(p, last) for p in state.all_players}
        placements = competition_placements(depth)
        return [
            {"player_id": pid, "placement": placements[pid], "score": state.match_wins[pid]}
            for pid in sorted(state.all_players, key=lambda p: placements[p])
        ]
