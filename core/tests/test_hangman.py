"""Hangman Duel module: pure calls with injected time."""

import json
import random

import pytest

from games import registry
from games.base import GameError
from games.constants import (
    HANGMAN_FLAG_WINDOW_MS,
    HANGMAN_MAX_WRONG,
    HANGMAN_POT,
    HANGMAN_REVEAL_MS,
    HANGMAN_SET_WORD_MS,
    HANGMAN_VOTE_MS,
    HANGMAN_WORD_MAX,
    HANGMAN_WORD_MIN,
    HANGMAN_WRONG_COST,
    OFFLINE_FORFEIT_MS,
)
from games.hangman import Hangman, round_award

HM = Hangman()
T0 = 2_000_000.0


def new(players=("a", "b", "c"), mode="group"):
    return HM.init(list(players), HM.validate_settings({"mode": mode}), random.Random(1), T0)


def act(state, pid, action, now=T0):
    return HM.handle_action(state, pid, action, now)


def set_word(state, word, hint=None, now=T0):
    action = {"type": "setWord", "word": word}
    if hint is not None:
        action["hint"] = hint
    return act(state, state.setter, action, now)[0]


def guess(state, pid, letter, now=T0):
    return act(state, pid, {"type": "guessLetter", "letter": letter}, now)


def errors(state, pid, action):
    with pytest.raises(GameError) as exc:
        HM.handle_action(state, pid, action, T0)
    return exc.value.code


def test_registered_and_settings() -> None:
    assert registry.get_game("hangman") is not None
    assert HM.validate_settings({}) == {"mode": "group"}
    with pytest.raises(GameError):
        HM.validate_settings({"mode": "solo"})
    with pytest.raises(GameError):
        HM.validate_settings({"rounds": 3})
    with pytest.raises(GameError):
        new(("a", "b", "c"), mode="duel")
    assert new(("a", "b"), mode="duel").setter == "a"


@pytest.mark.parametrize(
    "word", ["abcd", "x" * 11, "two words", "abcd1", "héllos", "", None, 42, "x" * 16]
)
def test_word_validation(word) -> None:
    assert errors(new(), "a", {"type": "setWord", "word": word}) == "INVALID_ACTION"


@pytest.mark.parametrize("hint", ["x" * 31, "<b>", 5])
def test_hint_validation(hint) -> None:
    assert (
        errors(new(), "a", {"type": "setWord", "word": "apples", "hint": hint}) == "INVALID_ACTION"
    )


def test_word_length_constants() -> None:
    assert (HANGMAN_WORD_MIN, HANGMAN_WORD_MAX) == (5, 10)
    assert (HANGMAN_POT, HANGMAN_WRONG_COST) == (12, 2)


def test_set_word_accepts_and_uppercases() -> None:
    state = set_word(new(), "Llama", hint="  An animal  ")
    assert state.word == "LLAMA" and state.hint == "An animal" and state.phase == "guessing"
    assert set_word(new(), "abcde", hint="   ").hint is None
    assert set_word(new(), "x" * HANGMAN_WORD_MAX).word == "X" * HANGMAN_WORD_MAX


def test_only_setter_sets_and_only_once() -> None:
    state = new()
    assert errors(state, "b", {"type": "setWord", "word": "apple"}) == "NOT_YOUR_TURN"
    state = set_word(state, "apple")
    assert errors(state, "a", {"type": "setWord", "word": "pears"}) == "NOT_YOUR_TURN"


def test_guess_validation() -> None:
    state = new()
    assert errors(state, "b", {"type": "guessLetter", "letter": "a"}) == "NOT_YOUR_TURN"
    state = set_word(state, "apple")
    assert errors(state, "a", {"type": "guessLetter", "letter": "a"}) == "INVALID_ACTION"
    for bad in ["", "ab", "1", "é", None]:
        assert errors(state, "b", {"type": "guessLetter", "letter": bad}) == "INVALID_ACTION"
    state, _ = guess(state, "b", "p")
    assert errors(state, "c", {"type": "guessLetter", "letter": "P"}) == "INVALID_ACTION"
    assert errors(state, "c", {"type": "jump"}) == "INVALID_ACTION"


def test_mask_with_repeated_letters_and_no_points_mid_round() -> None:
    state = set_word(new(), "LLAMA")
    state, _ = guess(state, "b", "l")
    assert HM.get_view(state, "c")["mask"] == ["L", "L", None, None, None]
    state, _ = guess(state, "c", "a")
    assert HM.get_view(state, "b")["mask"] == ["L", "L", "A", None, "A"]
    assert set(state.scores.values()) == {0}  # points only when the round ends


def solve(state, word, wrong=0, now=T0):
    """Guessers b and c take turns: `wrong` misses first, then the word's letters."""
    misses = [ch for ch in "ZQXJKVWY" if ch not in word.upper()][:wrong]
    events = []
    for i, letter in enumerate([*misses, *dict.fromkeys(word.upper())]):
        state, events = guess(state, state.guessers()[i % len(state.guessers())], letter, now)
    return state, events


@pytest.mark.parametrize("wrong", range(HANGMAN_MAX_WRONG))
def test_solved_round_splits_the_pot_by_wrong_guesses(wrong) -> None:
    state = set_word(new(), "apple")
    state, events = solve(state, "apple", wrong, T0 + 500)
    setter_share = HANGMAN_WRONG_COST * wrong
    each = (HANGMAN_POT - setter_share) / 2
    assert events[0]["kind"] == "roundOver" and events[0]["data"]["result"] == "guessers"
    assert events[0]["data"]["award"] == {"a": setter_share, "b": each, "c": each}
    assert state.scores == {"a": setter_share, "b": each, "c": each}


def test_figure_complete_gives_setter_the_pot() -> None:
    state = set_word(new(), "apple")
    for i, letter in enumerate("ZQXJKV"[:HANGMAN_MAX_WRONG]):
        state, events = guess(state, "b" if i % 2 else "c", letter)
    assert events[0]["data"]["result"] == "setter"
    assert state.scores == {"a": HANGMAN_POT, "b": 0, "c": 0}
    assert HM.get_view(state, "b")["wrongCount"] == HANGMAN_MAX_WRONG
    assert errors(state, "b", {"type": "guessLetter", "letter": "a"}) == "NOT_YOUR_TURN"


@pytest.mark.parametrize("wrong", range(HANGMAN_MAX_WRONG))
def test_word_length_does_not_change_points(wrong) -> None:
    short = solve(set_word(new(), "abcde"), "abcde", wrong)[0]
    long = solve(set_word(new(), "abcdefghij"), "abcdefghij", wrong)[0]
    assert short.scores == long.scores
    assert len(short.word) == HANGMAN_WORD_MIN and len(long.word) == HANGMAN_WORD_MAX


@pytest.mark.parametrize("players", range(2, 11))
@pytest.mark.parametrize("result", ["guessers", "setter", "skipped"])
@pytest.mark.parametrize("wrong", range(HANGMAN_MAX_WRONG))
def test_pot_invariant_every_outcome(players, result, wrong) -> None:
    """Setter plus guessers always share exactly HANGMAN_POT per round."""
    state = new([f"p{i}" for i in range(players)], mode="group")
    state.wrong = list("ZQXJKV"[:wrong])
    award = round_award(state, result)
    assert sum(award.values()) == pytest.approx(HANGMAN_POT)
    guesser_shares = {pts for pid, pts in award.items() if pid != state.setter}
    assert len(guesser_shares) == 1  # split equally among all guessers


def test_setter_rotates_in_join_order_everyone_guesses_every_other_word() -> None:
    state = new(("a", "b", "c"))
    setters, guessed_by = [], {}
    now = T0
    while not HM.is_over(state):
        setters.append(state.setter)
        state = set_word(state, "abcde", now=now)
        guessed_by[state.setter] = set(state.guessers())
        state, _ = solve(state, "abcde", 0, now)
        now = state.deadline
        state, _ = HM.tick(state, now)
    assert setters == ["a", "b", "c"]
    assert guessed_by == {"a": {"b", "c"}, "b": {"a", "c"}, "c": {"a", "b"}}
    assert state.scores == {"a": 12, "b": 12, "c": 12}  # equal play, equal points
    assert HM.next_deadline(state) is None
    view = HM.get_view(state, "a")
    assert view["phase"] == "done" and view["word"] == "ABCDE"


def test_setter_timeout_skips_round_and_guessers_share_the_pot() -> None:
    state = new()
    assert HM.next_deadline(state) == T0 + HANGMAN_SET_WORD_MS
    state, events = HM.tick(state, T0 + HANGMAN_SET_WORD_MS - 1)
    assert events == []
    state, events = HM.tick(state, T0 + HANGMAN_SET_WORD_MS)
    assert events[0]["data"] == {
        "round": 1, "setterId": "a", "word": None, "result": "skipped",
        "award": {"a": 0, "b": 6, "c": 6},
    }
    assert HM.get_view(state, "b")["canFlag"] is False  # nothing to flag
    state, _ = HM.tick(state, state.deadline)
    assert state.setter == "b" and state.phase == "setting"
    assert state.deadline == T0 + HANGMAN_SET_WORD_MS + HANGMAN_REVEAL_MS + HANGMAN_SET_WORD_MS


def test_offline_guessers_no_longer_end_the_round() -> None:
    state = set_word(new(), "apple")
    state, _ = HM.on_presence(state, "b", False, T0)
    state, _ = HM.on_presence(state, "c", False, T0)
    assert HM.next_deadline(state) is None
    state, events = HM.tick(state, T0 + OFFLINE_FORFEIT_MS + 1)
    assert events == [] and state.phase == "guessing"


@pytest.mark.parametrize("phase", ["setting", "guessing"])
def test_setter_forfeit_skips_the_round_with_no_points(phase) -> None:
    state = new(("a", "b", "c", "d"))
    if phase == "guessing":
        state = set_word(state, "apple")
        state, _ = guess(state, "b", "z")
    state, events = HM.forfeit(state, "a", T0 + 1, "quit")
    assert state.phase == "roundOver" and state.result == "skipped"
    assert events[0]["data"]["award"] == {} and state.award == {}
    assert state.scores == dict.fromkeys("abcd", 0.0)
    assert state.flag_until is None
    assert HM.get_view(state, "b")["word"] == ("APPLE" if phase == "guessing" else None)
    state, _ = HM.tick(state, state.deadline)
    assert state.setter == "b" and state.phase == "setting"


def test_a_forfeiters_own_setter_turn_is_dropped() -> None:
    state = new(("a", "b", "c", "d"))
    state, _ = HM.forfeit(state, "c", T0, "left")
    assert state.order == ["a", "b", "d"] and HM.get_view(state, "a")["total"] == 3
    setters = []
    for _ in range(3):
        setters.append(state.setter)
        state, _ = HM.tick(state, state.deadline)  # setting times out: skipped
        state, _ = HM.tick(state, state.deadline)
    assert setters == ["a", "b", "d"] and HM.is_over(state)


def test_past_setter_keeps_their_round_in_the_count() -> None:
    state = new(("a", "b", "c"))
    state, _ = HM.tick(state, state.deadline)
    state, _ = HM.tick(state, state.deadline)
    assert state.setter == "b"
    state, _ = HM.forfeit(state, "a", T0 + 1, "quit")
    assert state.order == ["a", "b", "c"] and state.guessers() == ["c"]


def test_guesser_forfeit_leaves_the_pot_to_the_others() -> None:
    state = set_word(new(("a", "b", "c", "d")), "abcde")
    state, _ = HM.forfeit(state, "d", T0 + 1, "offline")
    assert state.guessers() == ["b", "c"]
    with pytest.raises(GameError):
        act(state, "d", {"type": "guessLetter", "letter": "a"})
    state, _ = solve(state, "abcde", wrong=1)
    assert state.award == {"a": 2.0, "b": 5.0, "c": 5.0}
    assert state.scores["d"] == 0


def test_guesser_forfeit_mid_vote_recounts() -> None:
    state = set_word(new(("a", "b", "c", "d")), "abcde")
    state, _ = solve(state, "abcde")
    state, _ = act(state, "b", {"type": "flagWord"})
    state, _ = act(state, "c", {"type": "voteWord", "valid": False})
    assert state.phase == "flagVote"
    state, events = HM.forfeit(state, "d", T0 + 1, "quit")  # last voter gone: vote closes
    assert events[0]["kind"] == "flagResult" and events[0]["data"]["upheld"] is True
    assert state.scores == {"a": 0.0, "b": 6.0, "c": 6.0, "d": 0.0}
    assert state.setter == "b" and state.phase == "setting"


def test_forfeit_of_a_flag_voter_keeps_the_vote_open() -> None:
    state = set_word(new(("a", "b", "c", "d", "e")), "abcde")
    state, _ = solve(state, "abcde")
    state, _ = act(state, "b", {"type": "flagWord"})
    state, events = HM.forfeit(state, "c", T0 + 1, "quit")
    assert events == [] and state.flag["voters"] == ["b", "d", "e"]
    view = HM.get_view(state, "d")["flag"]
    assert view["voterIds"] == ["b", "d", "e"] and view["votedCount"] == 1


def test_results_by_total_score_and_ties_share() -> None:
    state = set_word(new(("a", "b")), "abcde")
    state, _ = solve(state, "abcde", wrong=1)  # a: 2, b: 10
    state, _ = HM.tick(state, state.deadline)
    state, _ = HM.tick(state, state.deadline)  # b never sets: a gets the whole pot
    state, _ = HM.tick(state, state.deadline)
    assert HM.get_results(state) == [
        {"player_id": "a", "placement": 1, "score": 14},
        {"player_id": "b", "placement": 2, "score": 10},
    ]
    tie = set_word(new(("a", "b")), "abcde")
    tie, _ = solve(tie, "abcde", wrong=3)  # a: 6, b: 6
    tie.round_index, tie.phase = 1, "done"
    assert [r["placement"] for r in HM.get_results(tie)] == [1, 1]


# ----- not-a-real-word flag ---------------------------------------------------------------


def round_over(players=("a", "b", "c", "d"), wrong=1):
    state = set_word(new(players), "qwerty")
    state, _ = solve(state, "qwerty", wrong, T0)
    return state


def test_flag_window_and_round_over_lasts_long_enough() -> None:
    state = round_over()
    assert state.deadline == T0 + max(HANGMAN_REVEAL_MS, HANGMAN_FLAG_WINDOW_MS)
    view = HM.get_view(state, "b")
    assert view["canFlag"] and view["flagUntil"] == T0 + HANGMAN_FLAG_WINDOW_MS
    assert not HM.get_view(state, "a")["canFlag"]  # the setter
    assert errors(state, "a", {"type": "flagWord"}) == "INVALID_ACTION"
    with pytest.raises(GameError):
        HM.handle_action(state, "b", {"type": "flagWord"}, T0 + HANGMAN_FLAG_WINDOW_MS + 1)


def test_flagging_disabled_with_two_players() -> None:
    state = round_over(("a", "b"))
    assert state.deadline == T0 + HANGMAN_REVEAL_MS
    assert HM.get_view(state, "b")["canFlag"] is False
    assert errors(state, "b", {"type": "flagWord"}) == "INVALID_ACTION"


def flagged(players=("a", "b", "c", "d"), by="b"):
    state = round_over(players)
    state, events = act(state, by, {"type": "flagWord"}, T0 + 1000)
    assert events == [{"kind": "wordFlagged", "data": {"round": 1, "flaggerId": by}}]
    return state


def vote(state, pid, valid, now=T0 + 2000):
    return act(state, pid, {"type": "voteWord", "valid": valid}, now)


def test_vote_rules_and_secrecy() -> None:
    state = flagged()
    assert state.phase == "flagVote" and state.deadline == T0 + 1000 + HANGMAN_VOTE_MS
    assert errors(state, "c", {"type": "flagWord"}) == "INVALID_ACTION"  # already flagged
    for pid, valid in (("b", False), ("a", True), ("c", "no")):  # flagger, setter, bad value
        assert errors(state, pid, {"type": "voteWord", "valid": valid}) == "INVALID_ACTION"
    state, events = vote(state, "c", True)
    assert events == []
    assert errors(state, "c", {"type": "voteWord", "valid": False}) == "INVALID_ACTION"
    view = HM.get_view(state, "d")
    assert view["flag"] == {
        "flaggerId": "b", "deadline": T0 + 1000 + HANGMAN_VOTE_MS, "voterIds": ["b", "c", "d"],
        "votedCount": 2, "canVote": True, "hasVoted": False,
    }
    assert HM.get_view(state, "c")["flag"]["hasVoted"] is True
    assert "votes" not in json.dumps(view)


def test_upheld_flag_gives_guessers_the_whole_pot() -> None:
    state = flagged()  # before: a 2, b c d 10/3 each
    state, _ = vote(state, "c", False)
    state, events = vote(state, "d", True)  # all voted: closes early; 2 of 3 Invalid
    result = events[0]["data"]
    assert events[0]["kind"] == "flagResult" and result["upheld"] is True
    assert (result["invalidVotes"], result["validVotes"]) == (2, 1)
    assert result["votes"] == {"b": False, "c": False, "d": True}
    assert result["award"] == {"a": 0, "b": 4, "c": 4, "d": 4}
    assert state.scores == pytest.approx({"a": 0, "b": 4, "c": 4, "d": 4})
    assert sum(state.scores.values()) == pytest.approx(HANGMAN_POT)
    assert state.phase == "setting" and state.setter == "b"


def test_tie_keeps_the_word() -> None:
    state = flagged(("a", "b", "c"))
    state, events = vote(state, "c", True)  # 1 Invalid (flagger) vs 1 Valid
    assert events[0]["data"]["upheld"] is False
    assert state.scores == pytest.approx({"a": 2, "b": 5, "c": 5})


def test_no_votes_keep_the_word_when_the_vote_times_out() -> None:
    state = flagged()  # 3 voters; only the flagger's Invalid counts
    state, events = HM.tick(state, T0 + 1000 + HANGMAN_VOTE_MS)
    assert events[0]["data"]["upheld"] is False and events[0]["data"]["invalidVotes"] == 1
    assert state.phase == "setting"
    assert sum(state.scores.values()) == pytest.approx(HANGMAN_POT)


def test_three_players_one_more_invalid_upholds() -> None:
    state = flagged(("a", "b", "c"))
    state, events = vote(state, "c", False)
    assert events[0]["data"]["upheld"] is True
    assert state.scores == pytest.approx({"a": 0, "b": 6, "c": 6})


@pytest.mark.parametrize("word", ["ZEBRA", "LLAMA", "QUIZZES", "XYLOPHONE"])
def test_guessers_never_receive_the_word(word) -> None:
    state = set_word(new(), word, hint="Something")
    assert HM.get_view(state, "a")["word"] == word
    letters = sorted(set(word))
    for i, letter in enumerate(letters[:-1]):
        for pid in ("b", "c"):
            view = HM.get_view(state, pid)
            blob = json.dumps(view)
            assert word not in blob and view["word"] is None
            hidden = [ch for ch in word if ch not in state.guessed]
            assert all(
                cell is None for cell, ch in zip(view["mask"], word, strict=True) if ch in hidden
            )
        state, _ = guess(state, "b" if i % 2 else "c", letter)
    state, _ = guess(state, "b", letters[-1])
    assert HM.get_view(state, "c")["word"] == word


def test_view_serializable() -> None:
    json.dumps(HM.get_view(new(), "b"))
    json.dumps(HM.get_view(flagged(), "c"))


def test_view_keys_match_protocol() -> None:
    assert set(HM.get_view(new(), "b")) == {
        "phase", "round", "total", "setterId", "isSetter", "mask", "word", "hint", "guessed",
        "wrong", "wrongCount", "maxWrong", "deadline", "result", "award", "scores", "pot",
        "wrongCost", "flagUntil", "canFlag", "flag",
    }
