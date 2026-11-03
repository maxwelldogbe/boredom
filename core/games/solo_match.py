"""Solo bot games: one game between a player and a bot (PROTOCOL.md 16).

SoloMatchGame runs one game of a two-player MatchEngine (tic-tac-toe, connect four, penalty
kick); SoloDots runs Dots and Boxes for two with a chosen first mover. Both offer the room
manager the same solo hooks: first_mover, to_move, bot_due, seat_view, fallback_action,
outcome and `realtime` (the bot picks its own moment to act).

A best-of-1 with no bracket: a draw is a draw (no replay, no coin flip). The first mover is
`settings["firstMover"]` when given (solo:again alternates it), else picked by the rng.
Turn timers work as in games/series.py: a timed-out move is replaced by a random legal one,
and MATCH_AFK_TIMEOUTS_TO_FORFEIT timeouts in a row lose the game.

Views keep the series shape (one match, always "playing" for both seats) so the existing
game screens render them unchanged.
"""

import random
from dataclasses import dataclass, field
from typing import Any

from games.base import ForfeitReason, GameError, GameEvent, GameModule, GameResult
from games.connect_four import ConnectFourEngine
from games.constants import MATCH_AFK_TIMEOUTS_TO_FORFEIT, SOLO_PENALTY_DIVE_GRACE_MS
from games.dots_and_boxes import DotsAndBoxes, DotsState, all_lines, compute_scores
from games.match_engine import MatchEngine
from games.penalty_kick import PenaltyKickEngine
from games.solo_guess_run import SoloGuessRun
from games.solo_hangman import SoloHangman
from games.solo_name_it import SoloNameIt
from games.tic_tac_toe import TicTacToeEngine

MATCH_ID = "solo"


@dataclass
class SoloMatchState:
    a: str  # the player, seat 1
    b: str  # the bot, seat 2
    first: str
    rng: random.Random
    game: Any
    timeouts: dict[str, int] = field(default_factory=dict)  # timeouts in a row
    winner: str | None = None
    draw: bool = False
    reason: str | None = None  # score | draw | afk | forfeit


class SoloMatchGame(GameModule):
    """Wraps an engine; `id` and `name` are the multiplayer game's, so clients reuse screens."""

    min_players = 2
    max_players = 2
    default_settings: dict[str, Any] = {}
    realtime = False

    def __init__(
        self,
        game_id: str,
        name: str,
        engine: MatchEngine,
        engine_settings: dict[str, Any] | None = None,
    ) -> None:
        self.id = game_id  # type: ignore[misc]
        self.name = name  # type: ignore[misc]
        self.engine = engine
        self.engine_settings = dict(engine_settings or {})

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        if set(settings) - {"firstMover"}:
            raise GameError("INVALID_ACTION", "Unknown setting.")
        return dict(settings)

    def init(self, players, settings, rng, now) -> SoloMatchState:
        if len(players) != 2:
            raise GameError("INVALID_ACTION", "A solo game needs a player and a bot.")
        a, b = players
        first = settings.get("firstMover")
        if first not in players:
            first = rng.choice(players)
        game = self.engine.init(a, b, dict(self.engine_settings), rng, first)
        game, _ = self.engine.tick(game, now)
        return SoloMatchState(a, b, first, rng, game, dict.fromkeys(players, 0))

    def to_move(self, state: SoloMatchState) -> list[str]:
        """Seats that owe a move now (empty once the game is decided)."""
        return [] if self.is_over(state) else self.engine.awaiting(state.game)

    def bot_due(self, state: SoloMatchState, bot_id: str) -> bool:
        """Whether the bot should act now."""
        return bot_id in self.to_move(state)

    def first_mover(self, state: SoloMatchState) -> str:
        return state.first

    def seat_view(self, state: SoloMatchState, player_id: str) -> dict[str, Any]:
        """The engine view of one seat: what a player sitting there may see (for the bot)."""
        return self.engine.view_for(state.game, player_id)

    def fallback_action(self, state: SoloMatchState, player_id: str, rng: random.Random) -> dict:
        """A legal action when the bot's chooser failed."""
        return self.engine.random_action(state.game, player_id, rng)

    # ----- actions and timers --------------------------------------------------------------

    def handle_action(self, state: SoloMatchState, player_id, action, now):
        if self.is_over(state):
            raise GameError("INVALID_ACTION", "The game is over.")
        if player_id not in (state.a, state.b):
            raise GameError("NOT_YOUR_TURN", "You are not in this game.")
        state.game, events = self.engine.apply(state.game, player_id, action, now)
        state.timeouts[player_id] = 0
        events = self._tag(events)
        self._after_move(state, events)
        return state, events

    def tick(self, state: SoloMatchState, now) -> tuple[Any, list[GameEvent]]:
        events: list[GameEvent] = []
        if self.is_over(state):
            return state, events
        deadline = self.engine.next_deadline(state.game)
        if deadline is None or now < deadline:
            return state, events
        owed = self.engine.awaiting(state.game)
        if not owed:
            state.game, engine_events = self.engine.tick(state.game, now)
            events.extend(self._tag(engine_events))
        for pid in owed:
            if pid not in self.engine.awaiting(state.game):
                continue
            action = self.engine.random_action(state.game, pid, state.rng)
            state.game, engine_events = self.engine.apply(state.game, pid, action, now)
            state.timeouts[pid] += 1
            events.append({"kind": "autoMove", "data": {"matchId": MATCH_ID, "playerId": pid}})
            events.extend(self._tag(engine_events))
            if state.timeouts[pid] >= MATCH_AFK_TIMEOUTS_TO_FORFEIT:
                self._end(state, self._other(state, pid), "afk", events)
                return state, events
        self._after_move(state, events)
        return state, events

    def forfeit(self, state: SoloMatchState, player_id: str, now: float, reason: ForfeitReason):
        events: list[GameEvent] = []
        if not self.is_over(state):
            self._end(state, self._other(state, player_id), "forfeit", events)
        return state, events

    def next_deadline(self, state: SoloMatchState) -> float | None:
        return None if self.is_over(state) else self.engine.next_deadline(state.game)

    def _after_move(self, state: SoloMatchState, events: list[GameEvent]) -> None:
        result, winner = self.engine.status(state.game)
        if result == "draw":
            self._end(state, None, "draw", events)
        elif result == "winner":
            self._end(state, winner, "score", events)

    def _end(
        self, state: SoloMatchState, winner: str | None, reason: str, events: list[GameEvent]
    ) -> None:
        state.winner, state.draw, state.reason = winner, winner is None, reason
        events.append(
            {
                "kind": "gameEnd",
                "data": {
                    "matchId": MATCH_ID,
                    "gameNo": 1,
                    "result": "draw" if winner is None else "winner",
                    "winner": winner,
                    "game": self.engine.public_view(state.game),
                },
            }
        )

    @staticmethod
    def _other(state: SoloMatchState, player_id: str) -> str:
        return state.b if player_id == state.a else state.a

    @staticmethod
    def _tag(events: list[GameEvent]) -> list[GameEvent]:
        return [{"kind": e["kind"], "data": {"matchId": MATCH_ID, **e["data"]}} for e in events]

    # ----- views and results ---------------------------------------------------------------

    def get_view(self, state: SoloMatchState, player_id: str) -> dict[str, Any]:
        over = self.is_over(state)
        seated = player_id in (state.a, state.b)
        game = (
            self.engine.view_for(state.game, player_id)
            if seated
            else self.engine.public_view(state.game)
        )
        match = {
            "id": MATCH_ID,
            "a": state.a,
            "b": state.b,
            "phase": "over" if over else "playing",
            "wins": {state.a: int(state.winner == state.a), state.b: int(state.winner == state.b)},
            "gameNo": 1,
            "draws": int(state.draw),
            "winner": state.winner,
            "reason": state.reason,
            "coinFlip": False,
            "lastGame": None,
        }
        return {
            "phase": "done" if over else "playing",
            "role": "player" if seated else "spectator",
            "bestOf": 1,
            "winsNeeded": 1,
            "bracketRound": 1,
            "matches": [dict(match)],
            "liveMatches": [] if over else [MATCH_ID],
            "match": {**match, "game": game},
            "watching": None,
            "alive": [state.a, state.b],
            "eliminated": [],
            "champion": state.winner,
        }

    def is_over(self, state: SoloMatchState) -> bool:
        return state.winner is not None or state.draw

    def outcome(self, state: SoloMatchState, player_id: str) -> str:
        """win, lose or draw for `player_id` once the game is over."""
        if state.draw:
            return "draw"
        return "win" if state.winner == player_id else "lose"

    def get_results(self, state: SoloMatchState) -> list[GameResult]:
        if state.draw:
            return [
                {"player_id": state.a, "placement": 1, "score": 0},
                {"player_id": state.b, "placement": 1, "score": 0},
            ]
        loser = self._other(state, state.winner or state.a)
        return [
            {"player_id": state.winner or state.a, "placement": 1, "score": 1},
            {"player_id": loser, "placement": 2, "score": 0},
        ]


class SoloPenalty(SoloMatchGame):
    """Penalty kick: the bot also keeps goal (a dive is optional, so `bot_due` covers it)."""

    realtime = True

    def bot_due(self, state: SoloMatchState, bot_id: str) -> bool:
        if self.is_over(state):
            return False
        game = state.game
        if game.phase == "aiming":
            return self.engine.shooter(game) == bot_id  # type: ignore[attr-defined]
        return (
            game.phase == "flight" and game.dive is None and self.engine.keeper(game) == bot_id  # type: ignore[attr-defined]
        )


class SoloDots(DotsAndBoxes):
    """Dots and Boxes for a player and a bot: the rules unchanged, the first mover chosen."""

    min_players = 2
    max_players = 2
    realtime = False

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        first = settings.get("firstMover")
        merged = super().validate_settings({k: v for k, v in settings.items() if k != "firstMover"})
        return {**merged, "firstMover": first} if first is not None else merged

    def init(self, players, settings, rng, now) -> DotsState:
        if len(players) != 2:
            raise GameError("INVALID_ACTION", "A solo game needs a player and a bot.")
        state = super().init(players, {"size": settings["size"]}, rng, now)
        first = settings.get("firstMover")
        if first not in players:
            first = rng.choice(players)
        state.order = [first, next(p for p in players if p != first)]
        return state

    def first_mover(self, state: DotsState) -> str:
        return state.order[0]

    def to_move(self, state: DotsState) -> list[str]:
        return [state.current] if state.phase == "playing" else []

    def bot_due(self, state: DotsState, bot_id: str) -> bool:
        return bot_id in self.to_move(state)

    def seat_view(self, state: DotsState, player_id: str) -> dict[str, Any]:
        return self.get_view(state, player_id)

    def fallback_action(self, state: DotsState, player_id: str, rng: random.Random) -> dict:
        free = [line for line in all_lines(state.size) if line not in state.lines]
        return {"type": "drawLine", "id": rng.choice(free)}

    def outcome(self, state: DotsState, player_id: str) -> str:
        scores = compute_scores(state)
        mine = scores[player_id]
        theirs = max(v for p, v in scores.items() if p != player_id)
        return "draw" if mine == theirs else "win" if mine > theirs else "lose"


SOLO_GAMES: dict[str, Any] = {
    "tic_tac_toe": SoloMatchGame("tic_tac_toe", "Tic-Tac-Toe", TicTacToeEngine()),
    "connect_four": SoloMatchGame("connect_four", "Connect Four", ConnectFourEngine()),
    "dots_and_boxes": SoloDots(),
    "penalty_kick": SoloPenalty(
        "penalty_kick",
        "Penalty Kick",
        PenaltyKickEngine(),
        {"kicksPerPlayer": 5, "keeperSpeed": "normal", "diveGraceMs": SOLO_PENALTY_DIVE_GRACE_MS},
    ),
}


# Solo challenges: one player, no bot, a score to beat (keyed by the public game id).
CHALLENGES: dict[str, Any] = {
    "guess_race": SoloGuessRun(),
    "name_it": SoloNameIt(),
    "hangman": SoloHangman(),
}

_STARTABLE: dict[str, Any] = {**SOLO_GAMES, **CHALLENGES}  # public game id -> module
_BY_MODULE_ID: dict[str, Any] = {m.id: m for m in _STARTABLE.values()}


def solo_module_for(game_id: str) -> Any:
    """The module solo:start runs for the public `game_id`, or None if it has no solo mode."""
    return _STARTABLE.get(game_id)


def get_solo_game(module_id: str) -> Any:
    """A solo module by its own id (the running game's id in a solo room), or None."""
    return _BY_MODULE_ID.get(module_id)


def is_challenge(module: Any) -> bool:
    """A solo challenge (no bot; scored runs) rather than a bot game."""
    return any(module is m for m in CHALLENGES.values())
