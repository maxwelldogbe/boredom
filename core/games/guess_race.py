"""Guess Race: Word Scramble and Emoji Guess in one module (plan section 8).

Everyone guesses at once. Every player who solves the round scores by finishing order
(server arrival order): rank k earns max(FLOOR, FIRST - STEP x (k - 1)). A round ends when
every online player has solved it or after GUESS_ROUND_MS. Hints appear at GUESS_HINT1_MS
and GUESS_HINT2_MS; the answer stays on screen for GUESS_REVEAL_MS before the next round.
"""

import random
from dataclasses import dataclass, field
from typing import Any

from games.base import GameError, GameEvent, GameModule, GameResult, competition_placements
from games.constants import (
    GUESS_HINT1_MS,
    GUESS_HINT2_MS,
    GUESS_RANK_POINTS_FIRST,
    GUESS_RANK_POINTS_FLOOR,
    GUESS_RANK_POINTS_STEP,
    GUESS_REVEAL_MS,
    GUESS_ROUND_MS,
    GUESS_TEXT_MAX,
)
from games.content import DIFFICULTIES, EMOJI, WORDS, EmojiPuzzle, Word
from games.normalize import normalize

CONTENT_KINDS = ("scramble", "emoji", "mixed")
ROUND_COUNTS = (5, 10, 15)


@dataclass(frozen=True)
class Prompt:
    """One planned round. `answer`, `answers` and `category` are secret until revealed."""

    kind: str  # "scramble" | "emoji"
    prompt: str
    answer: str
    answers: tuple[str, ...]  # normalized accepted answers
    category: str | None


@dataclass
class GuessRaceState:
    plan: list[Prompt]
    scores: dict[str, int]
    round: int = 1
    phase: str = "guessing"  # guessing | roundOver | done
    started_at: float = 0.0
    deadline: float = 0.0  # reveal end while roundOver
    hints_shown: int = 0
    solvers: list[dict[str, Any]] = field(default_factory=list)  # {playerId, rank, points}
    last_guess: dict[str, dict[str, Any]] = field(default_factory=dict)
    offline: list[str] = field(default_factory=list)

    @property
    def current(self) -> Prompt:
        return self.plan[self.round - 1]


def scramble(word: str, rng: random.Random) -> str:
    """Fisher-Yates shuffle repeated until the result differs from the word."""
    letters = list(word)
    while True:
        rng.shuffle(letters)
        if "".join(letters) != word:
            return "".join(letters).upper()


def rank_points(rank: int) -> int:
    """Points for the rank-th solver of a round (1-based). The only Guess Race scoring rule."""
    earned = GUESS_RANK_POINTS_FIRST - GUESS_RANK_POINTS_STEP * (rank - 1)
    return max(GUESS_RANK_POINTS_FLOOR, earned)


def first_letter(answer: str) -> str:
    """First letter or digit of the answer as shown, ignoring a leading "The "."""
    text = answer[4:] if answer.lower().startswith("the ") else answer
    return next((ch.upper() for ch in text if ch.isalnum()), "")


class GuessRace(GameModule):
    id = "guess_race"
    name = "Guess Race"
    min_players = 2
    max_players = 10
    default_settings: dict[str, Any] = {"content": "mixed", "rounds": 10, "difficulty": "mixed"}

    def __init__(
        self, words: tuple[Word, ...] = WORDS, emoji: tuple[EmojiPuzzle, ...] = EMOJI
    ) -> None:
        self.words = words
        self.emoji = emoji

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = {**self.default_settings, **settings}
        if set(merged) != set(self.default_settings):
            raise GameError("INVALID_ACTION", "Unknown setting.")
        if merged["content"] not in CONTENT_KINDS:
            raise GameError("INVALID_ACTION", "content must be scramble, emoji or mixed.")
        if type(merged["rounds"]) is not int or merged["rounds"] not in ROUND_COUNTS:
            raise GameError("INVALID_ACTION", "rounds must be 5, 10 or 15.")
        if merged["difficulty"] not in (*DIFFICULTIES, "mixed"):
            raise GameError("INVALID_ACTION", "difficulty must be easy, medium, hard or mixed.")
        return merged

    def init(self, players: list[str], settings: dict[str, Any], rng: random.Random, now: float):
        difficulty = settings["difficulty"]
        words = [w for w in self.words if difficulty in ("mixed", w.difficulty)]
        rng.shuffle(words)
        puzzles = list(self.emoji)
        rng.shuffle(puzzles)
        plan: list[Prompt] = []
        for _ in range(settings["rounds"]):
            kind = settings["content"]
            if kind == "mixed":
                kind = rng.choice(("scramble", "emoji"))
            if kind == "scramble":
                word = words.pop().word
                plan.append(Prompt("scramble", scramble(word, rng), word.upper(), (word,), None))
            else:
                p = puzzles.pop()
                answers = tuple(dict.fromkeys(normalize(a) for a in (p.answer, *p.alternatives)))
                plan.append(Prompt("emoji", p.emojis, p.answer, answers, p.category))
        return GuessRaceState(plan=plan, scores=dict.fromkeys(players, 0), started_at=now)

    def handle_action(
        self, state: GuessRaceState, player_id, action, now
    ) -> tuple[Any, list[GameEvent]]:
        if action.get("type") != "guess":
            raise GameError("INVALID_ACTION", "Unknown action.")
        text = action.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > GUESS_TEXT_MAX:
            raise GameError("INVALID_ACTION", f"Guess must be 1 to {GUESS_TEXT_MAX} characters.")
        if state.phase != "guessing" or now >= state.started_at + GUESS_ROUND_MS:
            raise GameError("INVALID_ACTION", "This round is over.")
        if any(s["playerId"] == player_id for s in state.solvers):
            raise GameError("INVALID_ACTION", "You already solved this one.")
        correct = normalize(text) in state.current.answers
        state.last_guess[player_id] = {"text": text.strip(), "correct": correct}
        if not correct:
            return state, []
        rank = len(state.solvers) + 1  # handled in server arrival order, so no exact ties
        points = rank_points(rank)
        state.scores[player_id] += points
        state.solvers.append({"playerId": player_id, "rank": rank, "points": points})
        return state, self._end_if_all_solved(state, now)

    def _end_if_all_solved(self, state: GuessRaceState, now: float) -> list[GameEvent]:
        solved = {s["playerId"] for s in state.solvers}
        online = [p for p in state.scores if p not in state.offline]
        if state.phase == "guessing" and online and all(p in solved for p in online):
            return [self._end_round(state, now)]
        return []

    def on_presence(self, state: GuessRaceState, player_id, online, now) -> tuple[Any, list]:
        if online:
            state.offline = [p for p in state.offline if p != player_id]
            return state, []
        if player_id not in state.offline:
            state.offline.append(player_id)
        return state, self._end_if_all_solved(state, now)

    def tick(self, state: GuessRaceState, now) -> tuple[Any, list[GameEvent]]:
        if state.phase == "guessing":
            if now >= state.started_at + GUESS_ROUND_MS:
                return state, [self._end_round(state, now)]
            elapsed = now - state.started_at
            state.hints_shown = (elapsed >= GUESS_HINT1_MS) + (elapsed >= GUESS_HINT2_MS)
        elif state.phase == "roundOver" and now >= state.deadline:
            if state.round == len(state.plan):
                state.phase = "done"
            else:
                state.round += 1
                state.phase, state.started_at, state.hints_shown = "guessing", now, 0
                state.solvers, state.last_guess = [], {}
        return state, []

    def _end_round(self, state: GuessRaceState, now: float) -> GameEvent:
        state.phase, state.deadline = "roundOver", now + GUESS_REVEAL_MS
        data = {"round": state.round, "answer": state.current.answer}
        return {"kind": "roundOver", "data": {**data, "solvers": [dict(s) for s in state.solvers]}}

    def next_deadline(self, state: GuessRaceState) -> float | None:
        if state.phase == "guessing":
            offsets = (GUESS_HINT1_MS, GUESS_HINT2_MS, GUESS_ROUND_MS)
            return state.started_at + offsets[state.hints_shown]
        if state.phase == "roundOver":
            return state.deadline
        return None

    def get_view(self, state: GuessRaceState, player_id: str) -> dict[str, Any]:
        current = state.current
        hints: list[dict[str, Any]] = []
        if state.hints_shown >= 1 or state.phase != "guessing":
            if current.kind == "emoji":
                hints.append({"type": "category", "value": current.category})
            else:
                hints.append({"type": "length", "value": len(current.answer)})
        if state.hints_shown >= 2 or state.phase != "guessing":
            hints.append({"type": "firstLetter", "value": first_letter(current.answer)})
        revealed = state.phase != "guessing"
        return {
            "phase": state.phase,
            "round": state.round,
            "total": len(state.plan),
            "kind": current.kind,
            "prompt": current.prompt,
            "hints": hints,
            "roundStartedAt": state.started_at,
            "roundEndsAt": state.started_at + GUESS_ROUND_MS,
            "revealEndsAt": state.deadline if state.phase == "roundOver" else None,
            "scores": dict(state.scores),
            "solvers": [dict(s) for s in state.solvers],
            "iSolved": any(s["playerId"] == player_id for s in state.solvers),
            "answer": current.answer if revealed else None,
            "myLastGuess": state.last_guess.get(player_id),
        }

    def is_over(self, state: GuessRaceState) -> bool:
        return state.phase == "done"

    def get_results(self, state: GuessRaceState) -> list[GameResult]:
        placements = competition_placements({p: float(s) for p, s in state.scores.items()})
        ranked = sorted(state.scores, key=lambda p: placements[p])
        return [
            {"player_id": p, "placement": placements[p], "score": state.scores[p]}
            for p in ranked
        ]
