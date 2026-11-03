"""Guess Race "Beat the clock": a solo challenge (PROTOCOL.md 16).

One global clock of SOLO_GUESS_RUN_MS. Puzzles come one at a time from the Guess Race pools
(scramble, emoji, or alternating for mixed), easy first, one level harder every
SOLO_LEVEL_EVERY solves (then staying hard); none repeats within a run. A correct guess (the
multiplayer checking, any listed anagram accepted) scores
max(SOLO_GUESS_POINTS_MIN, SOLO_GUESS_POINTS_MAX - SOLO_GUESS_POINTS_PER_SECOND x whole
seconds on the puzzle) and the next puzzle starts at once; a wrong guess costs nothing.
`skip` gives up a puzzle for SOLO_GUESS_SKIP_PENALTY_MS of run time; a puzzle unsolved after
SOLO_GUESS_PUZZLE_MS is skipped for free. After a skip the answer shows for SOLO_RESULT_MS
while the next puzzle already runs. Clues come as in the multiplayer game. The run ends when
the clock reaches zero; a puzzle in progress is lost. Score: the points; never the answer.
"""

import random
from dataclasses import dataclass, field
from typing import Any

from games.base import ForfeitReason, GameError, GameEvent, GameModule, GameResult
from games.constants import (
    GUESS_HINT1_MS,
    GUESS_HINT2_MS,
    GUESS_TEXT_MAX,
    SOLO_GUESS_POINTS_MAX,
    SOLO_GUESS_POINTS_MIN,
    SOLO_GUESS_POINTS_PER_SECOND,
    SOLO_GUESS_PUZZLE_MS,
    SOLO_GUESS_RUN_MS,
    SOLO_GUESS_SKIP_PENALTY_MS,
    SOLO_LEVEL_EVERY,
    SOLO_RESULT_MS,
)
from games.content import DIFFICULTIES
from games.guess_race import CONTENT_KINDS, GuessRace, Prompt, first_letter
from games.normalize import normalize

LEVELS = DIFFICULTIES  # easy, medium, hard


def puzzle_points(spent_ms: float) -> int:
    """Points for a puzzle solved `spent_ms` after it appeared."""
    seconds = int(max(0.0, spent_ms) // 1000)
    return max(
        SOLO_GUESS_POINTS_MIN, SOLO_GUESS_POINTS_MAX - SOLO_GUESS_POINTS_PER_SECOND * seconds
    )


@dataclass
class GuessRunState:
    player: str
    content: str  # scramble | emoji | mixed
    rng: random.Random
    run_ends_at: float
    puzzle: Prompt
    puzzle_started_at: float
    next_kind: str  # mixed: the kind of the next puzzle (alternates)
    used: set[str] = field(default_factory=set)
    score: int = 0
    solved: int = 0
    skipped: int = 0
    hints_shown: int = 0
    last_result: dict[str, Any] | None = None
    reveal_until: float | None = None  # a skipped answer is shown until then
    done: bool = False

    @property
    def level(self) -> int:
        """0, 1 or 2 (easy, medium, hard)."""
        return min(self.solved // SOLO_LEVEL_EVERY, len(LEVELS) - 1)


class SoloGuessRun(GameModule):
    id = "solo_guess_run"
    name = "Guess Race: Beat the clock"
    min_players = 1
    max_players = 1
    default_settings: dict[str, Any] = {"content": "mixed"}

    def __init__(self, race: GuessRace | None = None) -> None:
        self.race = race or GuessRace()
        self.emoji_pools = {
            d: [k for k, p in self.race.puzzles.items() if p.difficulty == d] for d in LEVELS
        }

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = {**self.default_settings, **settings}
        if set(merged) != set(self.default_settings) or merged["content"] not in CONTENT_KINDS:
            raise GameError("INVALID_ACTION", "content must be scramble, emoji or mixed.")
        return merged

    def init(self, players, settings, rng, now) -> GuessRunState:
        if len(players) != 1:
            raise GameError("INVALID_ACTION", "A run is for one player.")
        content = settings["content"]
        first_kind = rng.choice(("scramble", "emoji")) if content == "mixed" else content
        state = GuessRunState(
            player=players[0],
            content=content,
            rng=rng,
            run_ends_at=now + SOLO_GUESS_RUN_MS,
            puzzle=Prompt("scramble", "", "", (), None),
            puzzle_started_at=now,
            next_kind=first_kind,
        )
        self._next_puzzle(state, now)
        return state

    # ----- puzzles -----------------------------------------------------------------------

    def _pool(self, kind: str, level: str) -> list[str]:
        return self.emoji_pools[level] if kind == "emoji" else self.race.word_pools[level]

    def _next_puzzle(self, state: GuessRunState, now: float) -> None:
        kind = state.next_kind
        if state.content == "mixed":
            state.next_kind = "emoji" if kind == "scramble" else "scramble"
        level = LEVELS[state.level]
        fresh = [k for k in self._pool(kind, level) if k not in state.used]
        if not fresh:  # this level ran dry: any level not used yet, else start over
            fresh = [k for d in LEVELS for k in self._pool(kind, d) if k not in state.used]
        if not fresh:
            fresh = list(self._pool(kind, level))
        key = state.rng.choice(fresh)
        state.used.add(key)
        state.puzzle = self.race._prompt(key, state.rng)
        state.puzzle_started_at, state.hints_shown = now, 0

    def _give_up(self, state: GuessRunState, now: float, penalty: bool) -> None:
        state.skipped += 1
        if penalty:
            state.run_ends_at -= SOLO_GUESS_SKIP_PENALTY_MS
        state.last_result = {"correct": False, "points": 0, "answerIfSkipped": state.puzzle.answer}
        state.reveal_until = now + SOLO_RESULT_MS
        if now >= state.run_ends_at:
            state.done = True
            return
        self._next_puzzle(state, now)

    # ----- actions and timers ------------------------------------------------------------

    def handle_action(self, state: GuessRunState, player_id, action, now):
        if player_id != state.player:
            raise GameError("INVALID_ACTION", "This is not your run.")
        if state.done or now >= state.run_ends_at:
            raise GameError("INVALID_ACTION", "The run is over.")
        kind = action.get("type")
        if kind == "skip":
            self._give_up(state, now, penalty=True)
            return state, []
        if kind != "guess":
            raise GameError("INVALID_ACTION", "Unknown action.")
        text = action.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > GUESS_TEXT_MAX:
            raise GameError("INVALID_ACTION", f"Guess must be 1 to {GUESS_TEXT_MAX} characters.")
        if normalize(text) not in state.puzzle.answers:
            shown = state.last_result["answerIfSkipped"] if state.last_result else None
            state.last_result = {"correct": False, "points": 0, "answerIfSkipped": shown}
            return state, []
        points = puzzle_points(now - state.puzzle_started_at)
        state.score += points
        state.solved += 1
        state.last_result = {"correct": True, "points": points, "answerIfSkipped": None}
        state.reveal_until = None
        self._next_puzzle(state, now)
        return state, []

    def tick(self, state: GuessRunState, now) -> tuple[Any, list[GameEvent]]:
        if state.done:
            return state, []
        if now >= state.run_ends_at:
            state.done = True
            return state, []
        if state.reveal_until is not None and now >= state.reveal_until:
            state.reveal_until = None
            if state.last_result is not None:
                state.last_result = {**state.last_result, "answerIfSkipped": None}
        if now >= state.puzzle_started_at + SOLO_GUESS_PUZZLE_MS:
            self._give_up(state, now, penalty=False)
            return state, []
        elapsed = now - state.puzzle_started_at
        state.hints_shown = (elapsed >= GUESS_HINT1_MS) + (elapsed >= GUESS_HINT2_MS)
        return state, []

    def forfeit(self, state: GuessRunState, player_id: str, now: float, reason: ForfeitReason):
        state.done = True
        return state, []

    def next_deadline(self, state: GuessRunState) -> float | None:
        if state.done:
            return None
        start = state.puzzle_started_at
        times = [state.run_ends_at, start + SOLO_GUESS_PUZZLE_MS]
        if state.hints_shown < 1:
            times.append(start + GUESS_HINT1_MS)
        elif state.hints_shown < 2:
            times.append(start + GUESS_HINT2_MS)
        if state.reveal_until is not None:
            times.append(state.reveal_until)
        return min(times)

    # ----- views and results -------------------------------------------------------------

    def get_view(self, state: GuessRunState, player_id: str) -> dict[str, Any]:
        puzzle = state.puzzle
        hints: list[dict[str, Any]] = []
        if not state.done and state.hints_shown >= 1:
            if puzzle.kind == "emoji":
                hints.append({"type": "category", "value": puzzle.category})
            else:
                hints.append({"type": "length", "value": len(puzzle.answer)})
        if not state.done and state.hints_shown >= 2:
            hints.append({"type": "firstLetter", "value": first_letter(puzzle.answer)})
        return {
            "phase": "done" if state.done else "playing",
            "content": state.content,
            "kind": puzzle.kind,
            "prompt": None if state.done else puzzle.prompt,
            "hints": hints,
            "score": state.score,
            "solved": state.solved,
            "skipped": state.skipped,
            "level": state.level + 1,
            "runEndsAt": state.run_ends_at,
            "puzzleStartedAt": state.puzzle_started_at,
            "puzzleEndsAt": state.puzzle_started_at + SOLO_GUESS_PUZZLE_MS,
            "lastResult": dict(state.last_result) if state.last_result else None,
        }

    def is_over(self, state: GuessRunState) -> bool:
        return state.done

    def score(self, state: GuessRunState) -> int:
        return state.score

    def detail(self, state: GuessRunState) -> dict[str, Any]:
        return {"solved": state.solved, "skipped": state.skipped, "level": state.level + 1}

    def get_results(self, state: GuessRunState) -> list[GameResult]:
        return [{"player_id": state.player, "placement": 1, "score": state.score}]
