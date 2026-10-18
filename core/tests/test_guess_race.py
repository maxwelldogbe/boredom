"""Guess Race module: pure calls with seeded rng and injected time."""

import copy
import json
import random

import pytest

from games import registry
from games.base import GameError
from games.constants import (
    GUESS_HINT1_MS,
    GUESS_HINT2_MS,
    GUESS_REVEAL_MS,
    GUESS_ROUND_MS,
    GUESS_TEXT_MAX,
)
from games.content import EMOJI, WORDS
from games.guess_race import GuessRace, first_letter, scramble
from games.normalize import normalize

GR = GuessRace()
T0 = 5_000_000.0


def new(players=("a", "b", "c"), seed=1, **settings):
    return GR.init(list(players), GR.validate_settings(settings), random.Random(seed), T0)


def guess(state, pid, text, now=T0):
    return GR.handle_action(state, pid, {"type": "guess", "text": text}, now)


def finish_round(state, now):
    """Advance past the round end and the reveal pause."""
    state, _ = GR.tick(state, max(now, state.started_at + GUESS_ROUND_MS))
    state, _ = GR.tick(state, state.deadline)
    return state


def test_registered_and_settings() -> None:
    assert registry.get_game("guess_race") is not None
    assert GR.validate_settings({}) == {"content": "mixed", "rounds": 10, "difficulty": "mixed"}
    for bad in [{"rounds": 7}, {"rounds": True}, {"content": "x"}, {"difficulty": "x"}, {"y": 1}]:
        with pytest.raises(GameError):
            GR.validate_settings(bad)


@pytest.mark.parametrize("seed", range(50))
def test_scramble_never_equals_word(seed) -> None:
    rng = random.Random(seed)
    for w in WORDS:
        s = scramble(w.word, rng)
        assert s != w.word.upper() and sorted(s) == sorted(w.word.upper())


def test_scramble_is_identical_for_everyone() -> None:
    state = new(content="scramble")
    prompts = {GR.get_view(state, p)["prompt"] for p in ("a", "b", "c")}
    assert len(prompts) == 1


@pytest.mark.parametrize("content", ["scramble", "emoji", "mixed"])
def test_no_repeats_within_a_game(content) -> None:
    state = new(content=content, rounds=15, seed=9)
    answers = [p.answer for p in state.plan]
    assert len(answers) == len(set(answers)) == 15
    if content != "mixed":
        assert {p.kind for p in state.plan} == {content}


def test_mixed_uses_both_kinds_and_is_seeded() -> None:
    a = new(content="mixed", rounds=15, seed=4)
    b = new(content="mixed", rounds=15, seed=4)
    assert a.plan == b.plan
    assert {p.kind for p in a.plan} == {"scramble", "emoji"}


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
def test_difficulty_filters_words(difficulty) -> None:
    state = new(content="scramble", rounds=15, difficulty=difficulty)
    by_word = {w.word.upper(): w.difficulty for w in WORDS}
    assert {by_word[p.answer] for p in state.plan} == {difficulty}


def test_correct_guess_scores_with_speed_bonus() -> None:
    state = new(content="scramble")
    answer = state.current.answer
    state, events = guess(state, "b", f"  {answer.lower()}! ", T0 + 7_900)
    assert events == [
        {
            "kind": "roundOver",
            "data": {"round": 1, "answer": answer, "winnerId": "b", "points": 100 - 2 * 7},
        }
    ]
    assert state.scores == {"a": 0, "b": 86, "c": 0}
    assert state.phase == "roundOver" and state.deadline == T0 + 7_900 + GUESS_REVEAL_MS


@pytest.mark.parametrize(("elapsed_ms", "points"), [(0, 100), (999, 100), (1000, 98), (29_999, 42)])
def test_speed_points(elapsed_ms, points) -> None:
    state = new(content="scramble")
    state, events = guess(state, "a", state.current.answer, T0 + elapsed_ms)
    assert events[0]["data"]["points"] == points


def test_minimum_points_is_20() -> None:
    import games.guess_race as gr_module

    original = gr_module.GUESS_ROUND_MS
    gr_module.GUESS_ROUND_MS = 60_000
    try:
        state = new(content="scramble")
        state, events = guess(state, "a", state.current.answer, T0 + 59_000)
        assert events[0]["data"]["points"] == 20
    finally:
        gr_module.GUESS_ROUND_MS = original


def test_emoji_alternatives_and_normalization() -> None:
    state = new(content="emoji", rounds=15, seed=3)
    puzzle = next(p for p in EMOJI if p.answer == state.current.answer)
    for text in (puzzle.answer, *puzzle.alternatives):
        assert normalize(text) in state.current.answers
    lion = GuessRace(emoji=tuple(p for p in EMOJI if p.answer == "The Lion King") * 15)
    st = lion.init(["a", "b"], lion.validate_settings({"content": "emoji"}), random.Random(1), T0)
    for text in ("the lion king", "LION KING", "Lion-King!!", "  lionking "):
        action = {"type": "guess", "text": text}
        _, events = lion.handle_action(copy.deepcopy(st), "a", action, T0)
        assert events and events[0]["data"]["winnerId"] == "a", text


def test_wrong_guess_is_free_and_recorded() -> None:
    state = new()
    state, events = guess(state, "a", "definitely wrong")
    assert events == [] and state.scores["a"] == 0 and state.phase == "guessing"
    assert GR.get_view(state, "a")["myLastGuess"] == {"text": "definitely wrong", "correct": False}
    assert GR.get_view(state, "b")["myLastGuess"] is None


def test_first_correct_guess_wins_and_later_guesses_rejected() -> None:
    state = new(content="scramble")
    state, _ = guess(state, "a", state.current.answer, T0 + 1000)
    with pytest.raises(GameError) as exc:
        guess(state, "b", state.current.answer, T0 + 1500)
    assert exc.value.code == "INVALID_ACTION"
    assert state.scores["b"] == 0 and state.round_winner == "a"


@pytest.mark.parametrize("text", ["", "   ", "x" * (GUESS_TEXT_MAX + 1), None, 5])
def test_invalid_guess_text(text) -> None:
    with pytest.raises(GameError):
        GR.handle_action(new(), "a", {"type": "guess", "text": text}, T0)


def test_unknown_action_and_late_guess() -> None:
    state = new()
    with pytest.raises(GameError):
        GR.handle_action(state, "a", {"type": "buzz"}, T0)
    with pytest.raises(GameError):
        guess(state, "a", state.current.answer, T0 + GUESS_ROUND_MS)


def test_hint_timing_scramble() -> None:
    state = new(content="scramble")
    word = state.current.answer
    assert GR.get_view(state, "a")["hints"] == []
    assert GR.next_deadline(state) == T0 + GUESS_HINT1_MS
    state, _ = GR.tick(state, T0 + GUESS_HINT1_MS - 1)
    assert GR.get_view(state, "a")["hints"] == []
    state, _ = GR.tick(state, T0 + GUESS_HINT1_MS)
    assert GR.get_view(state, "a")["hints"] == [{"type": "length", "value": len(word)}]
    assert GR.next_deadline(state) == T0 + GUESS_HINT2_MS
    state, _ = GR.tick(state, T0 + GUESS_HINT2_MS)
    assert GR.get_view(state, "a")["hints"][1] == {"type": "firstLetter", "value": word[0]}
    assert GR.next_deadline(state) == T0 + GUESS_ROUND_MS


def test_hint_timing_emoji() -> None:
    state = new(content="emoji")
    state, _ = GR.tick(state, T0 + GUESS_HINT2_MS)
    hints = GR.get_view(state, "a")["hints"]
    assert hints == [
        {"type": "category", "value": state.current.category},
        {"type": "firstLetter", "value": first_letter(state.current.answer)},
    ]


def test_first_letter_skips_leading_the() -> None:
    assert first_letter("The Lion King") == "L"
    assert first_letter("E.T.") == "E"
    assert first_letter("Theater") == "T"
    assert first_letter("2 birds") == "2"


def test_timeout_without_winner_then_next_round() -> None:
    state = new(rounds=5)
    state, events = GR.tick(state, T0 + GUESS_ROUND_MS)
    assert events[0]["data"]["winnerId"] is None and events[0]["data"]["points"] == 0
    assert GR.get_view(state, "a")["answer"] == state.current.answer
    assert GR.next_deadline(state) == T0 + GUESS_ROUND_MS + GUESS_REVEAL_MS
    state, _ = GR.tick(state, T0 + GUESS_ROUND_MS + GUESS_REVEAL_MS - 1)
    assert state.round == 1
    state, _ = GR.tick(state, T0 + GUESS_ROUND_MS + GUESS_REVEAL_MS)
    view = GR.get_view(state, "a")
    assert view["round"] == 2 and view["phase"] == "guessing" and view["hints"] == []
    assert view["myLastGuess"] is None and view["answer"] is None


def test_game_ends_after_n_rounds_with_placements() -> None:
    state = new(("a", "b", "c", "d"), rounds=5)
    now = T0
    winners = ["a", "b", "a", "b", None]
    for winner in winners:
        if winner:
            state, _ = guess(state, winner, state.current.answer, state.started_at)
        now = state.started_at
        state = finish_round(state, now)
    assert GR.is_over(state) and GR.next_deadline(state) is None
    assert GR.get_results(state) == [
        {"player_id": "a", "placement": 1, "points": 200},
        {"player_id": "b", "placement": 1, "points": 200},
        {"player_id": "c", "placement": 3, "points": 0},
        {"player_id": "d", "placement": 3, "points": 0},
    ]


def string_values(value):
    """Every string inside a view (dict keys excluded)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from string_values(v)
    elif isinstance(value, list):
        for v in value:
            yield from string_values(v)


def assert_no_answer(view, prompt):
    for text in string_values(view):
        if text == prompt.prompt:
            continue  # the scrambled letters / emojis themselves
        assert normalize(text) not in prompt.answers, text
        assert prompt.answer.lower() not in text.lower(), text


@pytest.mark.parametrize("content", ["scramble", "emoji"])
@pytest.mark.parametrize("seed", range(10))
def test_answer_never_leaks_while_guessing(content, seed) -> None:
    state = new(content=content, rounds=15, seed=seed)
    for _ in range(15):
        for t in (0, GUESS_HINT1_MS, GUESS_HINT2_MS):
            state, _ = GR.tick(state, state.started_at + t)
            for pid in ("a", "b", "c"):
                assert_no_answer(GR.get_view(state, pid), state.current)
        state, _ = guess(state, "a", "wrong guess", state.started_at)
        assert_no_answer(GR.get_view(state, "b"), state.current)
        state = finish_round(state, state.started_at)


def test_answer_shown_after_round() -> None:
    state = new()
    state, _ = GR.tick(state, T0 + GUESS_ROUND_MS)
    assert GR.get_view(state, "b")["answer"] == state.current.answer


def test_view_serializable() -> None:
    json.dumps(GR.get_view(new(), "a"))
