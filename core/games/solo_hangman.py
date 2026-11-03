"""Hangman "Word streak": a solo challenge (PROTOCOL.md 16).

The server picks words from words.json (5 to 9 letters, a-z only) by difficulty: easy, then
one level harder every SOLO_LEVEL_EVERY words solved (staying hard); no word repeats within a
run. The player guesses letters; HANGMAN_MAX_WRONG wrong letters lose the word, which costs a
strike and is shown for SOLO_HANGMAN_RESULT_MS before the next word. A solved word adds 1 to
the streak and the next word starts at once. SOLO_HANGMAN_STRIKES strikes end the run. No
time limit per word. The word is never in the view before it is lost.
"""

import random
from dataclasses import dataclass, field
from typing import Any

from games.base import ForfeitReason, GameError, GameEvent, GameModule, GameResult
from games.constants import (
    HANGMAN_MAX_WRONG,
    SOLO_HANGMAN_RESULT_MS,
    SOLO_HANGMAN_STRIKES,
    SOLO_LEVEL_EVERY,
)
from games.content import DIFFICULTIES, WORDS, Word

WORD_LEN = (5, 9)
LETTERS = frozenset("abcdefghijklmnopqrstuvwxyz")


def word_pools(words: tuple[Word, ...] = WORDS) -> dict[str, list[str]]:
    """Playable words per difficulty."""
    lo, hi = WORD_LEN
    return {
        d: [
            w.word
            for w in words
            if w.difficulty == d and lo <= len(w.word) <= hi and set(w.word) <= LETTERS
        ]
        for d in DIFFICULTIES
    }


@dataclass
class HangmanRunState:
    player: str
    rng: random.Random
    word: str = ""
    correct: list[str] = field(default_factory=list)
    wrong: list[str] = field(default_factory=list)
    used: set[str] = field(default_factory=set)
    solved: int = 0
    strikes: int = 0
    word_number: int = 0
    phase: str = "guessing"  # guessing | lost (the lost word shows) | done
    reveal_until: float | None = None
    last_word: str | None = None

    @property
    def level(self) -> int:
        return min(self.solved // SOLO_LEVEL_EVERY, len(DIFFICULTIES) - 1)


class SoloHangman(GameModule):
    id = "solo_hangman"
    name = "Hangman: Word streak"
    min_players = 1
    max_players = 1
    default_settings: dict[str, Any] = {}

    def __init__(self, pools: dict[str, list[str]] | None = None) -> None:
        self.pools = pools if pools is not None else word_pools()

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        if settings:
            raise GameError("INVALID_ACTION", "Unknown setting.")
        return {}

    def init(self, players, settings, rng: random.Random, now) -> HangmanRunState:
        if len(players) != 1:
            raise GameError("INVALID_ACTION", "A run is for one player.")
        state = HangmanRunState(players[0], rng)
        self._next_word(state)
        return state

    def _next_word(self, state: HangmanRunState) -> None:
        level = DIFFICULTIES[state.level]
        fresh = [w for w in self.pools[level] if w not in state.used]
        if not fresh:
            fresh = [w for d in DIFFICULTIES for w in self.pools[d] if w not in state.used]
        if not fresh:
            fresh = list(self.pools[level])
        state.word = state.rng.choice(fresh)
        state.used.add(state.word)
        state.correct, state.wrong = [], []
        state.word_number += 1
        state.phase, state.reveal_until = "guessing", None

    def handle_action(self, state: HangmanRunState, player_id, action, now):
        if player_id != state.player:
            raise GameError("INVALID_ACTION", "This is not your run.")
        if action.get("type") != "guessLetter":
            raise GameError("INVALID_ACTION", "Unknown action.")
        if state.phase != "guessing":
            raise GameError("INVALID_ACTION", "Wait for the next word.")
        letter = action.get("letter")
        if not isinstance(letter, str) or len(letter) != 1 or letter.lower() not in LETTERS:
            raise GameError("INVALID_ACTION", "Pick a letter from A to Z.")
        letter = letter.lower()
        if letter in state.correct or letter in state.wrong:
            raise GameError("INVALID_ACTION", "You already picked that letter.")
        state.last_word = state.word
        if letter in state.word:
            state.correct.append(letter)
            if set(state.word) <= set(state.correct):
                state.solved += 1
                self._next_word(state)
            return state, []
        state.wrong.append(letter)
        if len(state.wrong) >= HANGMAN_MAX_WRONG:
            state.strikes += 1
            if state.strikes >= SOLO_HANGMAN_STRIKES:
                state.phase = "done"
            else:
                state.phase, state.reveal_until = "lost", now + SOLO_HANGMAN_RESULT_MS
        return state, []

    def tick(self, state: HangmanRunState, now) -> tuple[Any, list[GameEvent]]:
        if state.phase == "lost" and state.reveal_until is not None and now >= state.reveal_until:
            self._next_word(state)
        return state, []

    def forfeit(self, state: HangmanRunState, player_id: str, now: float, reason: ForfeitReason):
        state.phase = "done"
        return state, []

    def next_deadline(self, state: HangmanRunState) -> float | None:
        return state.reveal_until if state.phase == "lost" else None

    def get_view(self, state: HangmanRunState, player_id: str) -> dict[str, Any]:
        shown = state.phase in ("lost", "done") and len(state.wrong) >= HANGMAN_MAX_WRONG
        return {
            "phase": state.phase,
            "mask": [ch if ch in state.correct else None for ch in state.word],
            "guessed": {"correct": list(state.correct), "wrong": list(state.wrong)},
            "wrongCount": len(state.wrong),
            "maxWrong": HANGMAN_MAX_WRONG,
            "strikes": state.strikes,
            "maxStrikes": SOLO_HANGMAN_STRIKES,
            "solved": state.solved,
            "level": state.level + 1,
            "wordNumber": state.word_number,
            "revealedWord": state.word if shown else None,
            "revealUntil": state.reveal_until if state.phase == "lost" else None,
        }

    def is_over(self, state: HangmanRunState) -> bool:
        return state.phase == "done"

    def score(self, state: HangmanRunState) -> int:
        return state.solved

    def detail(self, state: HangmanRunState) -> dict[str, Any]:
        return {"strikes": state.strikes, "lastWord": state.last_word}

    def get_results(self, state: HangmanRunState) -> list[GameResult]:
        return [{"player_id": state.player, "placement": 1, "score": state.solved}]
