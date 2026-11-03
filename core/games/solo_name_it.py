"""Name It "Streak": a solo challenge (PROTOCOL.md 16).

The player names things in one topic (games/name_it_lists.py), one answer at a time with
NAMEIT_TURN_MS each. A listed answer (name or alias, matched on the folded form) adds 1 to
the streak; a wrong or unlisted answer, a repeat (any name of an entry already given) or a
timeout is a strike, and the answer timer restarts either way. SOLO_NAMEIT_STRIKES strikes
end the run, as does naming every entry (detail.completed). Score: the streak. The view
never holds an entry the player has not named.
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Any

from games.base import ForfeitReason, GameError, GameEvent, GameModule, GameResult
from games.constants import NAMEIT_TURN_MS, SOLO_NAMEIT_STRIKES
from games.name_it_lists import NAME_IT_TOPICS, TEXT_MAX, Topic, fold

logger = logging.getLogger("games.solo_name_it")

RANDOM = "random"


@dataclass
class NameItRunState:
    player: str
    topic: str
    turn_ends_at: float
    used: list[int] = field(default_factory=list)  # entry indexes, oldest first
    strikes: int = 0
    last_result: dict[str, str] | None = None
    done: bool = False
    completed: bool = False


class SoloNameIt(GameModule):
    id = "solo_name_it"
    name = "Name It: Streak"
    min_players = 1
    max_players = 1
    default_settings: dict[str, Any] = {"topic": RANDOM}

    def __init__(self, topics: dict[str, Topic] | None = None) -> None:
        self.topics = topics if topics is not None else NAME_IT_TOPICS

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = {**self.default_settings, **settings}
        if set(merged) != set(self.default_settings):
            raise GameError("INVALID_ACTION", "Unknown setting.")
        if merged["topic"] != RANDOM and merged["topic"] not in self.topics:
            raise GameError("INVALID_ACTION", "Unknown topic.")
        return merged

    def init(self, players, settings, rng: random.Random, now) -> NameItRunState:
        if len(players) != 1:
            raise GameError("INVALID_ACTION", "A run is for one player.")
        topic = settings["topic"]
        if topic == RANDOM:
            topic = rng.choice(sorted(self.topics))
        return NameItRunState(players[0], topic, now + NAMEIT_TURN_MS)

    def _strike(self, state: NameItRunState, kind: str, now: float) -> None:
        state.strikes += 1
        state.last_result = {"kind": kind}
        if state.strikes >= SOLO_NAMEIT_STRIKES:
            state.done = True
        else:
            state.turn_ends_at = now + NAMEIT_TURN_MS

    def handle_action(self, state: NameItRunState, player_id, action, now):
        if player_id != state.player:
            raise GameError("INVALID_ACTION", "This is not your run.")
        if state.done:
            raise GameError("INVALID_ACTION", "The run is over.")
        if action.get("type") != "submitAnswer":
            raise GameError("INVALID_ACTION", "Unknown action.")
        text = action.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > TEXT_MAX:
            raise GameError("INVALID_ACTION", f"Answer must be 1 to {TEXT_MAX} characters.")
        if now >= state.turn_ends_at:
            raise GameError("INVALID_ACTION", "Time is up for that answer.")
        topic = self.topics[state.topic]
        key = fold(text)
        entry = topic.index.get(key)
        if entry is None:
            logger.info("Unknown answer: topic=%s answer=%s", state.topic, key)
            self._strike(state, "wrong", now)
        elif entry in state.used:
            self._strike(state, "repeat", now)
        else:
            state.used.append(entry)
            state.last_result = {"kind": "correct"}
            if len(state.used) == len(topic.names):
                state.done = state.completed = True
            else:
                state.turn_ends_at = now + NAMEIT_TURN_MS
        return state, []

    def tick(self, state: NameItRunState, now) -> tuple[Any, list[GameEvent]]:
        if not state.done and now >= state.turn_ends_at:
            self._strike(state, "timeout", now)
        return state, []

    def forfeit(self, state: NameItRunState, player_id: str, now: float, reason: ForfeitReason):
        state.done = True
        return state, []

    def next_deadline(self, state: NameItRunState) -> float | None:
        return None if state.done else state.turn_ends_at

    def get_view(self, state: NameItRunState, player_id: str) -> dict[str, Any]:
        topic = self.topics[state.topic]
        return {
            "phase": "done" if state.done else "playing",
            "topic": {"id": topic.id, "name": topic.name, "emoji": topic.emoji},
            "streak": len(state.used),
            "strikes": state.strikes,
            "maxStrikes": SOLO_NAMEIT_STRIKES,
            "accepted": [topic.names[i] for i in reversed(state.used)],
            "turnEndsAt": None if state.done else state.turn_ends_at,
            "lastResult": dict(state.last_result) if state.last_result else None,
            "completed": state.completed,
        }

    def is_over(self, state: NameItRunState) -> bool:
        return state.done

    def score(self, state: NameItRunState) -> int:
        return len(state.used)

    def detail(self, state: NameItRunState) -> dict[str, Any]:
        return {"topic": state.topic, "strikes": state.strikes, "completed": state.completed}

    def variant(self, state: NameItRunState) -> str:
        """The SoloRecord variant: the topic actually played (also for "random")."""
        return state.topic

    def get_results(self, state: NameItRunState) -> list[GameResult]:
        return [{"player_id": state.player, "placement": 1, "score": len(state.used)}]
