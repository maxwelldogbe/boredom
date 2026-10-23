"""Name It Survival (plan section 12): name things in a topic in turn; slip up and you're out.

A player is out on a timeout, a repeated answer (after normalization) or a lost challenge.
Then the used list resets and the eliminated player picks the next topic (once). The first
topic is picked by the first player in seat order, from NAMEIT_TOPIC_SUGGESTIONS random
topics (typed topics only with allowCustomTopics). The last survivor wins.
"""

import random
import re
from dataclasses import dataclass, field
from typing import Any

from games.base import GameError, GameEvent, GameModule, GameResult
from games.constants import (
    NAMEIT_CHALLENGE_WINDOW_MS,
    NAMEIT_TOPIC_MS,
    NAMEIT_TOPIC_SUGGESTIONS,
    NAMEIT_TURN_MS,
    NAMEIT_VOTE_MS,
    NICKNAME_ALLOWED_PATTERN,
)
from games.content import TOPIC_MAX, TOPICS
from games.name_it_view import build_view
from games.normalize import normalize

ANSWER_MAX = 40
TURN_SECONDS = range(5, 31)
TOPIC_RE = re.compile(NICKNAME_ALLOWED_PATTERN)


@dataclass
class NameItState:
    order: list[str]
    alive: list[str]
    settings: dict[str, Any]
    rng: random.Random
    eliminated: list[str] = field(default_factory=list)  # in elimination order
    phase: str = "topicSelect"  # topicSelect | turn | challenge | done
    topic: str | None = None
    chooser: str | None = None
    suggestions: list[str] = field(default_factory=list)
    topic_deadline: float | None = None
    starter: str = ""
    current: str | None = None
    turn_deadline: float | None = None
    paused_ms: float | None = None  # turn time left while a challenge runs
    used: list[dict[str, str]] = field(default_factory=list)  # {playerId, text, normalized}
    window_until: float | None = None  # the latest answer can be challenged until then
    challenge: dict[str, Any] | None = None  # secret votes until it closes
    last_elimination: dict[str, Any] | None = None

    def turn_ms(self) -> int:
        return self.settings["turnSeconds"] * 1000

    def next_alive(self, player_id: str) -> str:
        """The first alive player after `player_id` in seat order (wrapping)."""
        i = self.order.index(player_id)
        for step in range(1, len(self.order) + 1):
            candidate = self.order[(i + step) % len(self.order)]
            if candidate in self.alive:
                return candidate
        return player_id


def compute_scores(state: NameItState) -> dict[str, int]:
    """Display score: players outlasted (n - placement). The only scoring rule here."""
    n = len(state.order)
    return {p: n - place for p, place in placements(state).items()}


def placements(state: NameItState) -> dict[str, int]:
    """Survivor 1st, then in reverse elimination order (first out is last)."""
    ranking = list(state.alive) + list(reversed(state.eliminated))
    return {p: i + 1 for i, p in enumerate(ranking)}


class NameIt(GameModule):
    id = "name_it"
    name = "Name It Survival"
    min_players = 3
    max_players = 10
    default_settings: dict[str, Any] = {
        "turnSeconds": NAMEIT_TURN_MS // 1000,
        "challenges": True,
        "allowCustomTopics": False,
    }

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = {**self.default_settings, **settings}
        if set(merged) != set(self.default_settings):
            raise GameError("INVALID_ACTION", "Unknown setting.")
        seconds = merged["turnSeconds"]
        if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds not in TURN_SECONDS:
            raise GameError("INVALID_ACTION", "turnSeconds must be 5 to 30.")
        for key in ("challenges", "allowCustomTopics"):
            if not isinstance(merged[key], bool):
                raise GameError("INVALID_ACTION", f"{key} must be true or false.")
        return merged

    def init(self, players: list[str], settings: dict[str, Any], rng: random.Random, now: float):
        state = NameItState(
            order=list(players), alive=list(players), settings=dict(settings), rng=rng
        )
        self._select_topic(state, chooser=players[0], starter=players[0], now=now)
        return state

    def _select_topic(self, state: NameItState, chooser: str, starter: str, now: float) -> None:
        state.phase, state.chooser, state.starter = "topicSelect", chooser, starter
        state.suggestions = state.rng.sample(TOPICS, min(NAMEIT_TOPIC_SUGGESTIONS, len(TOPICS)))
        state.topic, state.topic_deadline = None, now + NAMEIT_TOPIC_MS
        state.current = state.turn_deadline = state.paused_ms = None
        state.used, state.window_until, state.challenge = [], None, None

    def _start_turns(self, state: NameItState, topic: str, now: float) -> None:
        state.topic, state.topic_deadline, state.phase = topic, None, "turn"
        state.current, state.turn_deadline = state.starter, now + state.turn_ms()

    # ----- actions -------------------------------------------------------------------------

    def handle_action(self, state: NameItState, player_id, action, now) -> tuple[Any, list]:
        kind = action.get("type")
        handlers = {
            "chooseTopic": self._choose_topic,
            "submitAnswer": self._answer,
            "challenge": self._challenge,
            "vote": self._vote,
        }
        if kind not in handlers:
            raise GameError("INVALID_ACTION", "Unknown action.")
        if state.phase == "done":
            raise GameError("INVALID_ACTION", "The game is over.")
        return state, handlers[kind](state, player_id, action, now)

    def _choose_topic(self, state: NameItState, player_id: str, action: dict, now: float) -> list:
        if state.phase != "topicSelect" or player_id != state.chooser:
            raise GameError("NOT_YOUR_TURN", "Someone else is choosing the topic.")
        topic = action.get("topic")
        topic = topic.strip() if isinstance(topic, str) else ""
        if not state.settings["allowCustomTopics"]:
            if topic not in state.suggestions:
                raise GameError("INVALID_ACTION", "Pick one of the suggested topics.")
        elif not 0 < len(topic) <= TOPIC_MAX or not TOPIC_RE.fullmatch(topic):
            raise GameError("INVALID_ACTION", f"Topic must be 1 to {TOPIC_MAX} plain characters.")
        self._start_turns(state, topic, now)
        return []

    def _answer(self, state: NameItState, player_id: str, action: dict, now: float) -> list:
        if state.phase != "turn" or player_id != state.current:
            raise GameError("NOT_YOUR_TURN", "Wait for your turn.")
        text = action.get("text")
        text = text.strip() if isinstance(text, str) else ""
        if not 0 < len(text) <= ANSWER_MAX or not normalize(text):
            raise GameError("INVALID_ACTION", f"Answer must be 1 to {ANSWER_MAX} characters.")
        key = normalize(text)
        if any(u["normalized"] == key for u in state.used):
            return self._eliminate(state, player_id, "duplicate", text, now)
        state.used.append({"playerId": player_id, "text": text, "normalized": key})
        if state.settings["challenges"]:
            state.window_until = now + NAMEIT_CHALLENGE_WINDOW_MS
        state.current = state.next_alive(player_id)
        state.turn_deadline = now + state.turn_ms()
        return []

    def _challenge(self, state: NameItState, player_id: str, action: dict, now: float) -> list:
        if not state.settings["challenges"]:
            raise GameError("INVALID_ACTION", "Challenges are turned off for this game.")
        if state.phase != "turn" or state.window_until is None or now > state.window_until:
            raise GameError("INVALID_ACTION", "There is no answer to challenge right now.")
        answer = state.used[-1]
        if player_id == answer["playerId"] or player_id not in state.alive:
            raise GameError("INVALID_ACTION", "You can't challenge this answer.")
        voters = [p for p in state.alive if p not in (player_id, answer["playerId"])]
        state.phase, state.window_until = "challenge", None
        state.paused_ms = max(0.0, (state.turn_deadline or now) - now)
        state.turn_deadline = None
        state.challenge = {
            "answerIndex": len(state.used) - 1,
            "answererId": answer["playerId"],
            "challengerId": player_id,
            "voters": voters,
            "votes": {},
            "deadline": now + NAMEIT_VOTE_MS,
        }
        return self._resolve(state, now) if not voters else []

    def _vote(self, state: NameItState, player_id: str, action: dict, now: float) -> list:
        challenge = state.challenge
        if state.phase != "challenge" or challenge is None:
            raise GameError("INVALID_ACTION", "There is no vote right now.")
        if player_id not in challenge["voters"]:
            raise GameError("INVALID_ACTION", "You don't vote on this challenge.")
        if player_id in challenge["votes"]:
            raise GameError("INVALID_ACTION", "You already voted.")
        valid = action.get("valid")
        if not isinstance(valid, bool):
            raise GameError("INVALID_ACTION", "Vote valid: true or false.")
        challenge["votes"][player_id] = valid
        if len(challenge["votes"]) == len(challenge["voters"]):
            return self._resolve(state, now)
        return []

    def _resolve(self, state: NameItState, now: float) -> list[GameEvent]:
        """Close the vote: strict majority Invalid eliminates the answerer, else play resumes."""
        challenge = state.challenge
        assert challenge is not None
        votes = list(challenge["votes"].values())
        invalid, valid = votes.count(False), votes.count(True)
        answer = state.used[challenge["answerIndex"]]
        event: GameEvent = {
            "kind": "challengeResult",
            "data": {
                "answererId": challenge["answererId"],
                "challengerId": challenge["challengerId"],
                "text": answer["text"],
                "votes": dict(challenge["votes"]),
                "validVotes": valid,
                "invalidVotes": invalid,
                "valid": invalid <= valid,
            },
        }
        if invalid > valid:
            out = self._eliminate(state, challenge["answererId"], "challenge", answer["text"], now)
            return [event, *out]
        state.phase, state.challenge = "turn", None
        state.turn_deadline, state.paused_ms = now + (state.paused_ms or 0.0), None
        return [event]

    def _eliminate(
        self, state: NameItState, player_id: str, reason: str, text: str | None, now: float
    ) -> list[GameEvent]:
        topic = state.topic
        state.alive.remove(player_id)
        state.eliminated.append(player_id)
        state.last_elimination = {"playerId": player_id, "reason": reason, "text": text}
        data = {**state.last_elimination, "topic": topic}
        event: GameEvent = {"kind": "eliminated", "data": data}
        if len(state.alive) <= 1:
            state.phase = "done"
            state.topic_deadline = state.turn_deadline = state.paused_ms = None
            state.current, state.challenge, state.window_until = None, None, None
        else:
            self._select_topic(state, player_id, state.next_alive(player_id), now)
        return [event]

    # ----- timers ------------------------------------------------------------------------------

    def tick(self, state: NameItState, now) -> tuple[Any, list[GameEvent]]:
        deadline = self.next_deadline(state)
        if deadline is None or now < deadline:
            return state, []
        if state.phase == "topicSelect":
            self._start_turns(state, state.rng.choice(state.suggestions), now)
            return state, []
        if state.phase == "challenge":
            return state, self._resolve(state, now)
        assert state.current is not None
        return state, self._eliminate(state, state.current, "timeout", None, now)

    def next_deadline(self, state: NameItState) -> float | None:
        if state.phase == "topicSelect":
            return state.topic_deadline
        if state.phase == "challenge" and state.challenge is not None:
            return state.challenge["deadline"]
        return state.turn_deadline if state.phase == "turn" else None

    # ----- views and results -------------------------------------------------------------------

    def get_view(self, state: NameItState, player_id: str) -> dict[str, Any]:
        return build_view(state, player_id)

    def is_over(self, state: NameItState) -> bool:
        return state.phase == "done"

    def get_results(self, state: NameItState) -> list[GameResult]:
        places, scores = placements(state), compute_scores(state)
        ranked = sorted(places, key=lambda p: places[p])
        return [{"player_id": p, "placement": places[p], "score": scores[p]} for p in ranked]
