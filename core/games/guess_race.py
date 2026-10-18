"""Guess Race: Word Scramble and Emoji Guess in one module (plan section 8).

Everyone guesses at once; the first correct guess wins the round with a speed bonus.
Hints appear at GUESS_HINT1_MS and GUESS_HINT2_MS; a round lasts GUESS_ROUND_MS and its
answer stays on screen for GUESS_REVEAL_MS before the next one.
"""

import random
from dataclasses import dataclass, field
from typing import Any

from games.base import GameError, GameEvent, GameModule, GameResult, competition_placements
from games.constants import (
    GUESS_HINT1_MS,
    GUESS_HINT2_MS,
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
    round_winner: str | None = None
    round_points: int = 0
    last_guess: dict[str, dict[str, Any]] = field(default_factory=dict)

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
        correct = normalize(text) in state.current.answers
        state.last_guess[player_id] = {"text": text.strip(), "correct": correct}
        if not correct:
            return state, []
        elapsed_s = int((now - state.started_at) // 1000)
        points = max(20, 100 - 2 * elapsed_s)
        state.scores[player_id] += points
        return state, [self._end_round(state, now, player_id, points)]

    def tick(self, state: GuessRaceState, now) -> tuple[Any, list[GameEvent]]:
        if state.phase == "guessing":
            if now >= state.started_at + GUESS_ROUND_MS:
                return state, [self._end_round(state, now, None, 0)]
            elapsed = now - state.started_at
            state.hints_shown = (elapsed >= GUESS_HINT1_MS) + (elapsed >= GUESS_HINT2_MS)
        elif state.phase == "roundOver" and now >= state.deadline:
            if state.round == len(state.plan):
                state.phase = "done"
            else:
                state.round += 1
                state.phase, state.started_at, state.hints_shown = "guessing", now, 0
                state.round_winner, state.round_points, state.last_guess = None, 0, {}
        return state, []

    def _end_round(
        self, state: GuessRaceState, now: float, winner: str | None, points: int
    ) -> GameEvent:
        state.phase, state.deadline = "roundOver", now + GUESS_REVEAL_MS
        state.round_winner, state.round_points = winner, points
        data = {"round": state.round, "answer": state.current.answer, "winnerId": winner}
        return {"kind": "roundOver", "data": {**data, "points": points}}

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
            "roundWinner": state.round_winner,
            "roundPoints": state.round_points,
            "answer": current.answer if revealed else None,
            "myLastGuess": state.last_guess.get(player_id),
        }

    def is_over(self, state: GuessRaceState) -> bool:
        return state.phase == "done"

    def get_results(self, state: GuessRaceState) -> list[GameResult]:
        placements = competition_placements({p: float(s) for p, s in state.scores.items()})
        ranked = sorted(state.scores, key=lambda p: placements[p])
        return [
            {"player_id": p, "placement": placements[p], "points": state.scores[p]} for p in ranked
        ]
