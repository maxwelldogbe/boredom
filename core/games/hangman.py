"""Hangman Duel (plan section 9, fair scoring S2): one setter, the rest guess letters.

Each player sets a word once, in join order, and guesses every other player's word.
Every round is worth a fixed pot of HANGMAN_POT points, whatever the word:
- solved with w wrong letters: guessers share POT - WRONG_COST x w, the setter gets WRONG_COST x w;
- figure completes (or every guesser is gone): the setter gets the whole POT;
- the setter never sets a word: the guessers share the whole POT.
After a played round, any guesser may flag the word as not real (3+ players only); the
other guessers then vote (see games/hangman_flag.py).
"""

import random
import re
from dataclasses import dataclass, field
from typing import Any

from games.base import GameError, GameEvent, GameModule, GameResult, competition_placements
from games.constants import (
    HANGMAN_FLAG_WINDOW_MS,
    HANGMAN_HINT_MAX,
    HANGMAN_MAX_WRONG,
    HANGMAN_POT,
    HANGMAN_REVEAL_MS,
    HANGMAN_SET_WORD_MS,
    HANGMAN_WORD_MAX,
    HANGMAN_WORD_MIN,
    HANGMAN_WRONG_COST,
    NICKNAME_ALLOWED_PATTERN,
    OFFLINE_FORFEIT_MS,
)
from games.hangman_flag import FLAG_MIN_PLAYERS, close_vote, flag_view, start_flag, vote

WORD_RE = re.compile(rf"^[A-Za-z]{{{HANGMAN_WORD_MIN},{HANGMAN_WORD_MAX}}}$")
HINT_RE = re.compile(NICKNAME_ALLOWED_PATTERN)


@dataclass
class HangmanState:
    order: list[str]
    scores: dict[str, float]
    round_index: int = 0
    phase: str = "setting"  # setting | guessing | roundOver | flagVote | done
    deadline: float | None = None
    word: str | None = None  # secret, uppercase
    hint: str | None = None
    guessed: list[str] = field(default_factory=list)
    wrong: list[str] = field(default_factory=list)
    result: str | None = None  # guessers | setter | skipped
    award: dict[str, float] = field(default_factory=dict)  # this round's points
    flag_until: float | None = None  # a guesser may flag until then (roundOver)
    flag: dict[str, Any] | None = None  # {flaggerId, voters, votes (secret), upheld?}
    offline_since: dict[str, float] = field(default_factory=dict)

    @property
    def setter(self) -> str:
        return self.order[self.round_index]

    def guessers(self) -> list[str]:
        return [p for p in self.order if p != self.setter]


def round_award(state: HangmanState, result: str) -> dict[str, float]:
    """The round's points per player; always sums to HANGMAN_POT. The only scoring rule."""
    guessers = state.guessers()
    if result == "guessers":
        setter_share = float(HANGMAN_WRONG_COST * len(state.wrong))
    elif result == "setter":
        setter_share = float(HANGMAN_POT)
    else:  # skipped: the setter forfeits the pot
        setter_share = 0.0
    each = (HANGMAN_POT - setter_share) / len(guessers)
    return {state.setter: setter_share, **dict.fromkeys(guessers, each)}


def apply_award(state: HangmanState, award: dict[str, float], sign: int = 1) -> None:
    for pid, pts in award.items():
        state.scores[pid] += sign * pts


class Hangman(GameModule):
    id = "hangman"
    name = "Hangman Duel"
    min_players = 2
    max_players = 10
    default_settings: dict[str, Any] = {"mode": "group"}

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = {**self.default_settings, **settings}
        if set(merged) != set(self.default_settings):
            raise GameError("INVALID_ACTION", "Unknown setting.")
        if merged["mode"] not in ("group", "duel"):
            raise GameError("INVALID_ACTION", "mode must be group or duel.")
        return merged

    def init(self, players: list[str], settings: dict[str, Any], rng: random.Random, now: float):
        if settings["mode"] == "duel" and len(players) != 2:
            raise GameError("INVALID_ACTION", "Duel needs exactly 2 players. Choose group.")
        return HangmanState(
            order=list(players),
            scores=dict.fromkeys(players, 0.0),
            deadline=now + HANGMAN_SET_WORD_MS,
        )

    # ----- actions -------------------------------------------------------------------------

    def handle_action(self, state: HangmanState, player_id, action, now) -> tuple[Any, list]:
        kind = action.get("type")
        if kind == "setWord":
            return state, self._set_word(state, player_id, action, now)
        if kind == "guessLetter":
            return state, self._guess(state, player_id, action, now)
        if kind == "flagWord":
            if not self._can_flag(state, player_id, now):
                raise GameError("INVALID_ACTION", "You can't flag this word now.")
            return state, start_flag(state, player_id, now)
        if kind == "voteWord":
            events = vote(state, player_id, action.get("valid"), now)
            if state.phase == "flagVote" and state.flag and "upheld" in state.flag:
                self._next_round(state, now)
            return state, events
        raise GameError("INVALID_ACTION", "Unknown action.")

    def _set_word(self, state: HangmanState, player_id: str, action: dict, now: float) -> list:
        if state.phase != "setting" or player_id != state.setter:
            raise GameError("NOT_YOUR_TURN", "Only the setter can choose the word now.")
        word, hint = action.get("word"), action.get("hint")
        if not isinstance(word, str) or not WORD_RE.fullmatch(word):
            limits = f"{HANGMAN_WORD_MIN} to {HANGMAN_WORD_MAX}"
            raise GameError("INVALID_ACTION", f"Word must be {limits} letters A-Z.")
        if hint is not None:
            if not isinstance(hint, str):
                raise GameError("INVALID_ACTION", "Hint must be text.")
            hint = hint.strip() or None
            if hint and (len(hint) > HANGMAN_HINT_MAX or not HINT_RE.fullmatch(hint)):
                raise GameError(
                    "INVALID_ACTION", f"Hint must be up to {HANGMAN_HINT_MAX} plain characters."
                )
        state.word, state.hint = word.upper(), hint
        state.phase, state.deadline = "guessing", None
        return []

    def _guess(self, state: HangmanState, player_id: str, action: dict, now: float) -> list:
        if player_id == state.setter:
            raise GameError("INVALID_ACTION", "The setter can't guess.")
        if state.phase != "guessing":
            raise GameError("NOT_YOUR_TURN", "No word to guess right now.")
        letter = action.get("letter")
        if not isinstance(letter, str) or not re.fullmatch(r"[A-Za-z]", letter):
            raise GameError("INVALID_ACTION", "Guess a single letter A-Z.")
        letter = letter.upper()
        if letter in state.guessed:
            raise GameError("INVALID_ACTION", f"{letter} was already guessed.")
        assert state.word is not None
        state.guessed.append(letter)
        if letter in state.word:
            if all(ch in state.guessed for ch in state.word):
                return [self._end_round(state, "guessers", now)]
            return []
        state.wrong.append(letter)
        if len(state.wrong) >= HANGMAN_MAX_WRONG:
            return [self._end_round(state, "setter", now)]
        return []

    def _end_round(self, state: HangmanState, result: str, now: float) -> GameEvent:
        state.phase, state.result = "roundOver", result
        state.award = round_award(state, result)
        apply_award(state, state.award)
        flaggable = result != "skipped" and len(state.order) >= FLAG_MIN_PLAYERS
        state.flag_until = now + HANGMAN_FLAG_WINDOW_MS if flaggable else None
        state.deadline = max(now + HANGMAN_REVEAL_MS, state.flag_until or 0)
        data = {"round": state.round_index + 1, "setterId": state.setter, "word": state.word}
        award = {pid: round(pts, 2) for pid, pts in state.award.items()}
        return {"kind": "roundOver", "data": {**data, "result": result, "award": award}}

    def _can_flag(self, state: HangmanState, player_id: str, now: float) -> bool:
        return (
            state.phase == "roundOver"
            and state.flag_until is not None
            and now <= state.flag_until
            and player_id in state.guessers()
        )

    def _next_round(self, state: HangmanState, now: float) -> None:
        if state.round_index + 1 >= len(state.order):
            state.phase, state.deadline = "done", None
            return
        state.round_index += 1
        state.phase, state.deadline = "setting", now + HANGMAN_SET_WORD_MS
        state.word = state.hint = state.result = None
        state.guessed, state.wrong, state.award = [], [], {}
        state.flag_until, state.flag = None, None

    # ----- timers and presence ----------------------------------------------------------------

    def tick(self, state: HangmanState, now) -> tuple[Any, list[GameEvent]]:
        if state.phase == "setting" and state.deadline is not None and now >= state.deadline:
            return state, [self._end_round(state, "skipped", now)]
        if state.phase == "guessing":
            gone_at = self._all_guessers_gone_at(state)
            if gone_at is not None and now >= gone_at:
                return state, [self._end_round(state, "setter", now)]
        if state.phase == "flagVote" and state.deadline is not None and now >= state.deadline:
            events = close_vote(state)
            self._next_round(state, now)
            return state, events
        if state.phase == "roundOver" and state.deadline is not None and now >= state.deadline:
            self._next_round(state, now)
        return state, []

    def _all_guessers_gone_at(self, state: HangmanState) -> float | None:
        """When every guesser will have been offline for OFFLINE_FORFEIT_MS, else None."""
        guessers = state.guessers()
        if not all(g in state.offline_since for g in guessers):
            return None
        return max(state.offline_since[g] for g in guessers) + OFFLINE_FORFEIT_MS

    def on_presence(self, state: HangmanState, player_id, online, now) -> tuple[Any, list]:
        if online:
            state.offline_since.pop(player_id, None)
        else:
            state.offline_since.setdefault(player_id, now)
        return state, []

    def next_deadline(self, state: HangmanState) -> float | None:
        if state.phase == "guessing":
            return self._all_guessers_gone_at(state)
        return state.deadline

    # ----- views and results -------------------------------------------------------------------

    def get_view(self, state: HangmanState, player_id: str) -> dict[str, Any]:
        revealed = state.phase in ("roundOver", "flagVote", "done")
        is_setter = player_id == state.setter and state.phase != "done"
        word = state.word or ""
        return {
            "phase": state.phase,
            "round": state.round_index + 1,
            "total": len(state.order),
            "setterId": state.setter,
            "isSetter": is_setter,
            "mask": [ch if ch in state.guessed or revealed else None for ch in word],
            "word": state.word if (is_setter or revealed) else None,
            "hint": state.hint,
            "guessed": list(state.guessed),
            "wrong": list(state.wrong),
            "wrongCount": len(state.wrong),
            "maxWrong": HANGMAN_MAX_WRONG,
            "deadline": state.deadline,
            "result": state.result,
            "award": {pid: round(pts, 2) for pid, pts in state.award.items()},
            "scores": {pid: round(pts, 2) for pid, pts in state.scores.items()},
            "pot": HANGMAN_POT,
            "wrongCost": HANGMAN_WRONG_COST,
            "flagUntil": state.flag_until if state.phase == "roundOver" else None,
            "canFlag": state.phase == "roundOver" and state.flag_until is not None
            and player_id in state.guessers(),
            "flag": flag_view(state, player_id),
        }

    def is_over(self, state: HangmanState) -> bool:
        return state.phase == "done"

    def get_results(self, state: HangmanState) -> list[GameResult]:
        scores = {pid: round(pts, 2) for pid, pts in state.scores.items()}
        placements = competition_placements(scores)
        ranked = sorted(scores, key=lambda p: placements[p])
        return [{"player_id": p, "placement": placements[p], "score": scores[p]} for p in ranked]
