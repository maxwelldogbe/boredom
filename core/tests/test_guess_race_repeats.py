"""Guess Race content rules: anagrams, scrambles that are never words, no repeats in a room."""

import copy
import random

import pytest

from games.content import BLOCKLIST, EMOJI, WORDS, EmojiPuzzle, Word
from games.content_rules import is_blocked, letters_key
from games.guess_race import GuessRace, scramble
from games.normalize import normalize
from tests.conftest import make_profile

GR = GuessRace()
T0 = 1_000_000.0
WORD_SET = {w.word for w in WORDS}


def settings(**over):
    return GR.validate_settings({"rounds": 15, **over})


def key(prompt):
    return (
        ("w:" + letters_key(prompt.answer))
        if prompt.kind == "scramble"
        else ("e:" + normalize(prompt.answer))
    )


def play_games(n, rng, **over):
    """Plan `n` consecutive games in one room; returns each game's prompts."""
    used: frozenset[str] = frozenset()
    games = []
    for _ in range(n):
        state, used = GR.start(["a", "b"], settings(**over), rng, T0, used)
        games.append(state.plan)
    return games


# ----- anagrams and scrambles ------------------------------------------------------------------


def test_every_anagram_in_the_list_is_accepted() -> None:
    groups = [g for g in GR.anagrams.values() if len(g) > 1]
    assert len(groups) > 100
    for group in groups:
        prompt = GR._prompt("w:" + letters_key(group[0]), random.Random(1))
        for word in group:
            assert normalize(word) in prompt.answers, (word, group)
            solved, _ = GR.handle_action(
                copy.deepcopy(state_with(prompt)), "a", {"type": "guess", "text": word}, T0
            )
            assert solved.solvers and solved.solvers[0]["playerId"] == "a", word


def test_listen_silent_enlist() -> None:
    group = GR.anagrams[letters_key("listen")]
    assert {"listen", "silent", "enlist"} <= set(group)
    prompt = GR._prompt("w:" + letters_key("listen"), random.Random(5))
    assert {"listen", "silent", "enlist"} <= set(prompt.answers)
    assert prompt.prompt.lower() not in WORD_SET


def state_with(prompt):
    state = GR.init(["a", "b"], settings(content="scramble", rounds=5), random.Random(0), T0)
    state.plan[0] = prompt
    return state


@pytest.mark.parametrize("seed", range(3))
def test_a_scramble_is_never_a_listed_or_blocked_word(seed) -> None:
    rng = random.Random(seed)
    for w in WORDS:
        shown = scramble(w.word, rng, GR.refused).lower()
        assert shown != w.word and sorted(shown) == sorted(w.word)
        assert shown not in WORD_SET and not is_blocked(shown, BLOCKLIST), (w.word, shown)


def test_scramble_falls_back_when_shuffles_keep_failing() -> None:
    # Only one arrangement of "abcd" besides itself is allowed.
    allowed = "dcba"
    shown = scramble("abcd", random.Random(0), lambda s: s != allowed)
    assert shown == allowed.upper()


def test_scramble_shown_in_a_game_is_never_a_word() -> None:
    for plan in play_games(10, random.Random(3), content="scramble"):
        for prompt in plan:
            assert prompt.prompt.lower() not in WORD_SET
            assert prompt.prompt.lower() != prompt.answer.lower()


# ----- no repeats --------------------------------------------------------------------------------


@pytest.mark.parametrize("content", ["scramble", "emoji", "mixed"])
@pytest.mark.parametrize("difficulty", ["easy", "mixed"])
def test_no_puzzle_repeats_across_20_games_in_a_room(content, difficulty) -> None:
    games = play_games(20, random.Random(42), content=content, difficulty=difficulty)
    keys = [key(p) for plan in games for p in plan]
    assert len(keys) == 300 and len(set(keys)) == 300


def test_seeded_rooms_are_reproducible() -> None:
    a = [[p.prompt for p in plan] for plan in play_games(3, random.Random(9))]
    b = [[p.prompt for p in plan] for plan in play_games(3, random.Random(9))]
    assert a == b


def test_mixed_difficulty_keeps_the_bands_balanced() -> None:
    plans = play_games(40, random.Random(1), content="scramble", difficulty="mixed")
    lengths = [len(p.answer) for plan in plans for p in plan]
    easy = sum(n <= 5 for n in lengths)
    hard = sum(n >= 8 for n in lengths)
    assert 140 <= easy <= 260 and 140 <= hard <= 260  # about a third each of 600 rounds


def small_game(words=20, puzzles=20):
    word_list = tuple(
        Word(w, d)
        for d, base in (("easy", "bcd"), ("medium", "bcdfg"), ("hard", "bcdfghj"))
        for w in (base + chr(97 + i) for i in range(words))
    )
    emoji = tuple(EmojiPuzzle("🐶", f"Answer {i}", (), "Thing", "easy") for i in range(puzzles))
    return GuessRace(words=word_list, emoji=emoji)


def test_used_set_resets_only_when_a_pool_is_exhausted() -> None:
    game = small_game(puzzles=20)
    rules = game.validate_settings({"content": "emoji", "rounds": 5})
    rng, used, seen = random.Random(7), frozenset(), []
    for _ in range(4):  # 4 x 5 = all 20 puzzles, no reset yet
        state, used = game.start(["a", "b"], rules, rng, T0, used)
        seen += [p.answer for p in state.plan]
    assert len(set(seen)) == 20 and len(used) == 20
    state, used = game.start(["a", "b"], rules, rng, T0, used)  # exhausted: a new cycle
    assert len(used) == 5 and {"e:" + normalize(p.answer) for p in state.plan} == set(used)


def test_an_exhausted_pool_uses_its_last_unused_puzzles_first() -> None:
    game = small_game(puzzles=20)
    rules = game.validate_settings({"content": "emoji", "rounds": 15})
    rng = random.Random(2)
    first, used = game.start(["a", "b"], rules, rng, T0, frozenset())
    second, used = game.start(["a", "b"], rules, rng, T0, used)
    left = {p.answer for p in game.emoji} - {p.answer for p in first.plan}
    assert left <= {p.answer for p in second.plan}  # the 5 never shown come first
    assert len({p.answer for p in second.plan}) == 15  # still no repeat inside a game
    assert len(used) == 15


def test_one_pool_resetting_leaves_the_others_alone() -> None:
    game = small_game(words=20, puzzles=20)
    used = frozenset(f"e:answer{i}" for i in range(18)) | frozenset({"w:" + letters_key("bcda")})
    rules = game.validate_settings({"content": "emoji", "rounds": 5})
    _, after = game.start(["a", "b"], rules, random.Random(0), T0, used)
    assert "w:" + letters_key("bcda") in after  # the word pool was not touched


def test_tiny_pools_still_fill_every_round() -> None:
    lion = GuessRace(emoji=tuple(p for p in EMOJI if p.answer == "The Lion King") * 15)
    state = lion.init(
        ["a", "b"], lion.validate_settings({"content": "emoji"}), random.Random(1), T0
    )
    assert len(state.plan) == 10 and {p.answer for p in state.plan} == {"The Lion King"}


# ----- through the room manager ----------------------------------------------------------------


async def test_the_room_remembers_puzzles_across_games(connect, manager) -> None:
    host = await connect()
    ack = await host.request("room:create", {"profile": make_profile("Host")})
    code = ack["data"]["room"]["code"]
    ann = await connect()
    await ann.request("room:join", {"code": code, "profile": make_profile("Ann")})
    rng = random.Random(11)
    manager.rng_factory = lambda: rng
    room = manager.rooms[code]
    seen: list[str] = []
    for _ in range(20):
        rules = {"content": "mixed", "rounds": 5, "difficulty": "mixed"}
        assert (await host.request("room:selectGame", {"gameId": "guess_race", "settings": rules}))[
            "ok"
        ]
        assert (await host.request("game:start"))["ok"]
        seen += [key(p) for p in room.game_state.plan]
        assert (await host.request("game:end"))["ok"]
    assert len(seen) == 100 and len(set(seen)) == 100
    assert set(seen) <= room.used_content["guess_race"]
    state = await host.wait_push("room:state", lambda d: d["status"] == "lobby")
    assert "usedContent" not in state and "used_content" not in state  # server-side only
