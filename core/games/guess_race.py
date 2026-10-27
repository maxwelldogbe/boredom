"""Guess Race: Word Scramble and Emoji Guess in one module (plan section 8).

Everyone guesses at once. Every player who solves the round scores by finishing order
(server arrival order): rank k earns max(FLOOR, FIRST - STEP x (k - 1)). The first correct
guess leaves everyone else GUESS_SOLVED_WINDOW_MS to solve it too; the round ends then, when
every online player has solved it, or after GUESS_ROUND_MS, whichever comes first. Hints
appear at GUESS_HINT1_MS and GUESS_HINT2_MS; the answer stays on screen for GUESS_REVEAL_MS
before the next round.
A forfeiting player takes no further part: they can't guess and no round waits for them.

A scramble accepts every listed word made of the same letters (LISTEN, SILENT, ENLIST), and is
never itself a listed or blocked word. Puzzles do not repeat within a room: `start` skips the
content keys the room has used and only reuses a pool once it is exhausted.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import permutations
from typing import Any

from games.base import (
    ForfeitReason,
    GameError,
    GameEvent,
    GameModule,
    GameResult,
    competition_placements,
)
from games.constants import (
    GUESS_HINT1_MS,
    GUESS_HINT2_MS,
    GUESS_RANK_POINTS_FIRST,
    GUESS_RANK_POINTS_FLOOR,
    GUESS_RANK_POINTS_STEP,
    GUESS_REVEAL_MS,
    GUESS_ROUND_MS,
    GUESS_SOLVED_WINDOW_MS,
    GUESS_TEXT_MAX,
)
from games.content import BLOCKLIST, DIFFICULTIES, EMOJI, WORDS, EmojiPuzzle, Word
from games.content_rules import Blocklist, anagram_index, is_blocked, letters_key
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
    closes_at: float | None = None  # set by the first correct guess of the round
    deadline: float = 0.0  # reveal end while roundOver
    hints_shown: int = 0
    solvers: list[dict[str, Any]] = field(default_factory=list)  # {playerId, rank, points}
    last_guess: dict[str, dict[str, Any]] = field(default_factory=dict)
    offline: list[str] = field(default_factory=list)
    forfeited: list[str] = field(default_factory=list)

    @property
    def current(self) -> Prompt:
        return self.plan[self.round - 1]

    @property
    def ends_at(self) -> float:
        """When guessing stops this round: 30 s in, or the solved window if that is sooner."""
        full = self.started_at + GUESS_ROUND_MS
        return full if self.closes_at is None else min(full, self.closes_at)


SHUFFLE_TRIES = 50


def scramble(
    word: str, rng: random.Random, refused: Callable[[str], bool] = lambda s: False
) -> str:
    """Shuffle until the result is neither the word nor `refused` (a listed or blocked word).

    Content validation guarantees an acceptable arrangement exists; after SHUFFLE_TRIES
    shuffles one is chosen from the full list of arrangements.
    """
    letters = list(word)
    for _ in range(SHUFFLE_TRIES):
        rng.shuffle(letters)
        shown = "".join(letters)
        if shown != word and not refused(shown):
            return shown.upper()
    options = sorted({"".join(p) for p in permutations(word)} - {word})
    return rng.choice([o for o in options if not refused(o)]).upper()


def draw(pool: list[str], n: int, used: frozenset[str], rng: random.Random) -> list[str]:
    """`n` keys from `pool`, unused ones first. Only an exhausted pool is reused."""
    fresh = [k for k in pool if k not in used]
    if len(fresh) >= n:
        return rng.sample(fresh, n)
    picks = rng.sample(fresh, len(fresh))
    while len(picks) < n:  # exhausted: start the pool over, still avoiding this game's picks
        rest = [k for k in pool if k not in picks] or list(pool)
        picks += rng.sample(rest, min(n - len(picks), len(rest)))
    return picks


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
        self,
        words: tuple[Word, ...] = WORDS,
        emoji: tuple[EmojiPuzzle, ...] = EMOJI,
        blocklist: Blocklist = BLOCKLIST,
    ) -> None:
        self.words = words
        self.emoji = emoji
        self.blocklist = blocklist
        self.word_set = frozenset(w.word for w in words)
        self.anagrams = anagram_index(w.word for w in words)
        # Content keys: anagrams share one key, so LISTEN and SILENT never both come up.
        self.word_pools: dict[str, list[str]] = {
            d: list(dict.fromkeys("w:" + letters_key(w.word) for w in words if w.difficulty == d))
            for d in DIFFICULTIES
        }
        self.puzzles = {"e:" + normalize(p.answer): p for p in emoji}
        self.emoji_pool = list(self.puzzles)

    def refused(self, shown: str) -> bool:
        """A scramble may not show a listed word or a blocked one."""
        return shown in self.word_set or is_blocked(shown, self.blocklist)

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
        return self.start(players, settings, rng, now, frozenset())[0]

    def start(
        self,
        players: list[str],
        settings: dict[str, Any],
        rng: random.Random,
        now: float,
        used: frozenset[str],
    ) -> tuple[GuessRaceState, frozenset[str]]:
        """Plan every round from content this room has not used yet.

        Mixed content picks scramble or emoji per round; mixed difficulty picks the word band
        per round, so each band comes up equally often whatever its size.
        """
        pools: list[str] = []  # the pool each round draws from, in round order
        for _ in range(settings["rounds"]):
            kind = settings["content"]
            if kind == "mixed":
                kind = rng.choice(("scramble", "emoji"))
            if kind == "emoji":
                pools.append("emoji")
            elif settings["difficulty"] == "mixed":
                pools.append(rng.choice(DIFFICULTIES))
            else:
                pools.append(settings["difficulty"])
        drawn: dict[str, list[str]] = {}
        for name in dict.fromkeys(pools):
            keys = self.emoji_pool if name == "emoji" else self.word_pools[name]
            drawn[name] = draw(keys, pools.count(name), used, rng)
            if any(k in used for k in drawn[name]):
                used = used - frozenset(keys)  # exhausted: a new cycle starts with these picks
            used = used | frozenset(drawn[name])
        plan = [self._prompt(drawn[name].pop(), rng) for name in pools]
        state = GuessRaceState(plan=plan, scores=dict.fromkeys(players, 0), started_at=now)
        return state, used

    def _prompt(self, key: str, rng: random.Random) -> Prompt:
        if key.startswith("w:"):
            group = self.anagrams[key[2:]]
            word = rng.choice(group)
            shown = scramble(word, rng, self.refused)
            return Prompt("scramble", shown, word.upper(), tuple(sorted(group)), None)
        p = self.puzzles[key]
        answers = tuple(dict.fromkeys(normalize(a) for a in (p.answer, *p.alternatives)))
        return Prompt("emoji", p.emojis, p.answer, answers, p.category)

    def handle_action(
        self, state: GuessRaceState, player_id, action, now
    ) -> tuple[Any, list[GameEvent]]:
        if action.get("type") != "guess":
            raise GameError("INVALID_ACTION", "Unknown action.")
        text = action.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > GUESS_TEXT_MAX:
            raise GameError("INVALID_ACTION", f"Guess must be 1 to {GUESS_TEXT_MAX} characters.")
        if player_id in state.forfeited:
            raise GameError("INVALID_ACTION", "You are out of this game.")
        if state.phase != "guessing" or now >= state.ends_at:
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
        if state.closes_at is None:
            state.closes_at = now + GUESS_SOLVED_WINDOW_MS
        return state, self._end_if_all_solved(state, now)

    def _end_if_all_solved(self, state: GuessRaceState, now: float) -> list[GameEvent]:
        solved = {s["playerId"] for s in state.solvers}
        gone = set(state.offline) | set(state.forfeited)
        online = [p for p in state.scores if p not in gone]
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

    def forfeit(
        self, state: GuessRaceState, player_id: str, now: float, reason: ForfeitReason
    ) -> tuple[Any, list[GameEvent]]:
        if player_id not in state.forfeited:
            state.forfeited.append(player_id)
        return state, self._end_if_all_solved(state, now)

    def tick(self, state: GuessRaceState, now) -> tuple[Any, list[GameEvent]]:
        if state.phase == "guessing":
            if now >= state.ends_at:
                return state, [self._end_round(state, now)]
            elapsed = now - state.started_at
            state.hints_shown = (elapsed >= GUESS_HINT1_MS) + (elapsed >= GUESS_HINT2_MS)
        elif state.phase == "roundOver" and now >= state.deadline:
            if state.round == len(state.plan):
                state.phase = "done"
            else:
                state.round += 1
                state.phase, state.started_at, state.hints_shown = "guessing", now, 0
                state.closes_at = None
                state.solvers, state.last_guess = [], {}
        return state, []

    def _end_round(self, state: GuessRaceState, now: float) -> GameEvent:
        state.phase, state.deadline = "roundOver", now + GUESS_REVEAL_MS
        data = {"round": state.round, "answer": state.current.answer}
        return {"kind": "roundOver", "data": {**data, "solvers": [dict(s) for s in state.solvers]}}

    def next_deadline(self, state: GuessRaceState) -> float | None:
        if state.phase == "guessing":
            offsets = (GUESS_HINT1_MS, GUESS_HINT2_MS, GUESS_ROUND_MS)
            return min(state.started_at + offsets[state.hints_shown], state.ends_at)
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
            "roundEndsAt": state.ends_at,
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
            {"player_id": p, "placement": placements[p], "score": state.scores[p]} for p in ranked
        ]
