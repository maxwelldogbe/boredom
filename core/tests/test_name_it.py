"""Name It Survival module: pure calls with injected time."""

import json
import random

import pytest

from games import registry
from games.base import GameError
from games.constants import (
    NAMEIT_CHALLENGE_WINDOW_MS,
    NAMEIT_TOPIC_MS,
    NAMEIT_TOPIC_SUGGESTIONS,
    NAMEIT_TURN_MS,
    NAMEIT_VOTE_MS,
)
from games.content import TOPICS
from games.name_it import NameIt

NI = NameIt()
T0 = 5_000_000.0
TURN = NAMEIT_TURN_MS


def new(players=("a", "b", "c", "d"), seed=1, topic="Fruits", **settings):
    settings.setdefault("allowCustomTopics", True)  # scripted topics are typed
    state = NI.init(list(players), NI.validate_settings(settings), random.Random(seed), T0)
    if topic:
        state, _ = NI.handle_action(state, players[0], {"type": "chooseTopic", "topic": topic}, T0)
    return state


def act(state, pid, action, now=T0):
    return NI.handle_action(state, pid, action, now)


def answer(state, text, now=T0):
    return act(state, state.current, {"type": "submitAnswer", "text": text}, now)


def code_of(state, pid, action, now=T0):
    with pytest.raises(GameError) as exc:
        act(state, pid, action, now)
    return exc.value.code


def test_registered_and_settings() -> None:
    assert isinstance(registry.get_game("name_it"), NameIt)
    assert NI.validate_settings({}) == {
        "turnSeconds": 10, "challenges": True, "allowCustomTopics": False,
    }
    for bad in ({"turnSeconds": 4}, {"turnSeconds": 31}, {"turnSeconds": True},
                {"turnSeconds": "10"}, {"challenges": 1}, {"allowCustomTopics": "no"},
                {"lives": 3}):
        with pytest.raises(GameError):
            NI.validate_settings(bad)
    assert (NI.min_players, NI.max_players) == (3, 10)


def test_first_topic_is_chosen_by_the_first_player_from_suggestions_or_typed() -> None:
    state = new(topic=None)
    view = NI.get_view(state, "a")
    assert view["phase"] == "topicSelect" and view["isTopicChooser"]
    assert len(set(view["suggestions"])) == NAMEIT_TOPIC_SUGGESTIONS
    assert set(view["suggestions"]) <= set(TOPICS)
    assert view["topicDeadline"] == T0 + NAMEIT_TOPIC_MS
    assert not NI.get_view(state, "b")["isTopicChooser"]
    assert code_of(state, "b", {"type": "chooseTopic", "topic": "Cars"}) == "NOT_YOUR_TURN"
    for bad in ("", "   ", "x" * 41, 7, None, "Cars; DROP"):
        assert code_of(state, "a", {"type": "chooseTopic", "topic": bad}) == "INVALID_ACTION"
    assert code_of(state, "a", {"type": "submitAnswer", "text": "x"}) == "NOT_YOUR_TURN"
    state, _ = act(state, "a", {"type": "chooseTopic", "topic": "  Things that are blue "})
    assert state.topic == "Things that are blue" and state.phase == "turn"
    assert state.current == "a" and state.turn_deadline == T0 + TURN


def test_topic_falls_back_to_a_random_suggestion() -> None:
    state = new(topic=None)
    assert NI.next_deadline(state) == T0 + NAMEIT_TOPIC_MS
    state, _ = NI.tick(state, T0 + NAMEIT_TOPIC_MS - 1)
    assert state.phase == "topicSelect"
    suggestions = list(state.suggestions)
    state, _ = NI.tick(state, T0 + NAMEIT_TOPIC_MS)
    assert state.phase == "turn" and state.topic in suggestions


def test_turn_order_and_answer_validation() -> None:
    state = new()
    assert code_of(state, "b", {"type": "submitAnswer", "text": "pear"}) == "NOT_YOUR_TURN"
    for bad in ("", "   ", "!!!", "x" * 41, None, 3):
        assert code_of(state, "a", {"type": "submitAnswer", "text": bad}) == "INVALID_ACTION"
    state, events = answer(state, "Apple", now=T0 + 2000)
    assert events == [] and state.current == "b" and state.turn_deadline == T0 + 2000 + TURN
    state, _ = answer(state, "Pear")
    state, _ = answer(state, "Kiwi")
    state, _ = answer(state, "Mango")
    assert state.current == "a"
    used = [u["text"] for u in NI.get_view(state, "c")["used"]]
    assert used == ["Apple", "Pear", "Kiwi", "Mango"]


def test_duplicate_after_normalization_eliminates_and_eliminated_picks_next_topic() -> None:
    state = new()
    state, _ = answer(state, "Apple")
    state, events = answer(state, "  the APPLE! ", now=T0 + 500)
    assert events == [{
        "kind": "eliminated",
        "data": {"playerId": "b", "reason": "duplicate", "text": "the APPLE!", "topic": "Fruits"},
    }]
    assert state.alive == ["a", "c", "d"] and state.used == []
    view = NI.get_view(state, "b")
    assert view["phase"] == "topicSelect" and view["isTopicChooser"] and view["topic"] is None
    assert view["lastElimination"]["playerId"] == "b"
    assert code_of(state, "b", {"type": "submitAnswer", "text": "x"}) == "NOT_YOUR_TURN"
    state, _ = act(state, "b", {"type": "chooseTopic", "topic": state.suggestions[0]}, T0 + 600)
    assert state.current == "c"  # the next alive player after b starts
    assert "b" not in state.alive and state.chooser == "b"


def test_timeout_eliminates_the_current_player() -> None:
    state = new(turnSeconds=5)
    state, _ = answer(state, "Apple")
    assert NI.next_deadline(state) == T0 + 5000
    state, events = NI.tick(state, T0 + 5000)
    assert events[0]["data"]["reason"] == "timeout" and events[0]["data"]["playerId"] == "b"


def challenge(state, by="c", now=T0 + 1000):
    return act(state, by, {"type": "challenge"}, now)


def test_challenge_window_and_who_may_challenge() -> None:
    state = new()
    assert code_of(state, "b", {"type": "challenge"}) == "INVALID_ACTION"  # nothing answered
    state, _ = answer(state, "Apple")
    view = NI.get_view(state, "c")
    assert view["canChallenge"] and view["challengeWindow"] == {
        "answerIndex": 0, "until": T0 + NAMEIT_CHALLENGE_WINDOW_MS,
    }
    assert not NI.get_view(state, "a")["canChallenge"]
    assert code_of(state, "a", {"type": "challenge"}) == "INVALID_ACTION"
    late = T0 + NAMEIT_CHALLENGE_WINDOW_MS + 1
    assert code_of(state, "c", {"type": "challenge"}, now=late) == "INVALID_ACTION"
    state, _ = answer(state, "Pear")  # a new answer: only it can be challenged now
    assert NI.get_view(state, "a")["challengeWindow"]["answerIndex"] == 1
    off = new(challenges=False)
    off, _ = answer(off, "Apple")
    assert NI.get_view(off, "b")["challengeWindow"] is None
    assert code_of(off, "b", {"type": "challenge"}) == "INVALID_ACTION"


def test_challenge_pauses_the_turn_and_a_tie_resumes_it() -> None:
    state, _ = answer(new(), "Apple", now=T0)  # b's turn until T0 + TURN
    state, events = challenge(state, by="c", now=T0 + 3000)
    assert events == [] and state.phase == "challenge" and state.turn_deadline is None
    view = NI.get_view(state, "b")
    assert view["pausedMs"] == TURN - 3000 and view["challenge"]["canVote"]
    assert view["challenge"]["voterIds"] == ["b", "d"]
    assert NI.next_deadline(state) == T0 + 3000 + NAMEIT_VOTE_MS
    assert code_of(state, "b", {"type": "submitAnswer", "text": "Pear"}) == "NOT_YOUR_TURN"
    for pid, vote in (("a", False), ("c", False)):  # answerer and challenger don't vote
        assert code_of(state, pid, {"type": "vote", "valid": vote}) == "INVALID_ACTION"
    assert code_of(state, "b", {"type": "vote", "valid": "no"}) == "INVALID_ACTION"
    state, events = act(state, "b", {"type": "vote", "valid": True}, T0 + 4000)
    assert events == []
    assert code_of(state, "b", {"type": "vote", "valid": False}) == "INVALID_ACTION"
    state, events = act(state, "d", {"type": "vote", "valid": False}, T0 + 5000)
    result = events[0]
    assert result["kind"] == "challengeResult" and result["data"]["valid"] is True
    assert (result["data"]["validVotes"], result["data"]["invalidVotes"]) == (1, 1)
    assert state.phase == "turn" and state.current == "b" and "a" in state.alive
    assert state.turn_deadline == T0 + 5000 + TURN - 3000


def test_majority_invalid_eliminates_the_answerer() -> None:
    state, _ = answer(new(), "Banana")
    state, _ = challenge(state, by="b")
    state, _ = act(state, "c", {"type": "vote", "valid": False})
    state, events = act(state, "d", {"type": "vote", "valid": False})
    assert [e["kind"] for e in events] == ["challengeResult", "eliminated"]
    assert events[0]["data"]["valid"] is False
    assert events[1]["data"] == {
        "playerId": "a", "reason": "challenge", "text": "Banana", "topic": "Fruits",
    }
    assert state.phase == "topicSelect" and state.chooser == "a" and state.starter == "b"


def test_no_votes_keep_the_answer_when_the_vote_times_out() -> None:
    state, _ = answer(new(("a", "b", "c", "d", "e")), "Fig")
    state, _ = challenge(state, by="b", now=T0 + 1000)
    state, _ = act(state, "c", {"type": "vote", "valid": False}, T0 + 2000)
    view = NI.get_view(state, "d")
    assert view["challenge"]["votedCount"] == 1 and "votes" not in view["challenge"]
    assert set(view["challenge"]) == {
        "answerIndex", "answererId", "challengerId", "text", "deadline", "voterIds",
        "votedCount", "canVote", "hasVoted",
    }
    assert NI.get_view(state, "c")["challenge"]["hasVoted"] is True  # only your own status
    state, events = NI.tick(state, T0 + 1000 + NAMEIT_VOTE_MS)
    assert events[0]["data"]["valid"] is False  # 1 invalid vs 0 valid is a strict majority
    state2, _ = answer(new(("a", "b", "c", "d", "e")), "Fig")
    state2, _ = challenge(state2, by="b", now=T0 + 1000)
    state2, events = NI.tick(state2, T0 + 1000 + NAMEIT_VOTE_MS)
    assert events[0]["data"]["valid"] is True and state2.phase == "turn"


def test_with_two_alive_a_challenge_has_no_voters_and_keeps_the_answer() -> None:
    state = new(("a", "b", "c"))
    state, _ = NI.tick(state, T0 + TURN)  # a times out
    state, _ = act(state, "a", {"type": "chooseTopic", "topic": "Colors"}, T0 + TURN)
    state, _ = answer(state, "Red", now=T0 + TURN)
    state, events = challenge(state, by=state.current, now=T0 + TURN + 100)
    assert events[0]["data"]["valid"] is True and state.phase == "turn"


def test_last_survivor_wins_and_placement_is_by_elimination_order() -> None:
    state = new(("a", "b", "c"))
    state, _ = NI.tick(state, T0 + TURN)  # a out
    state, _ = act(state, "a", {"type": "chooseTopic", "topic": "Colors"}, T0 + TURN)
    assert state.current == "b"
    state, _ = answer(state, "Red", now=T0 + TURN)
    state, events = answer(state, "red", now=T0 + TURN)  # c repeats: out
    assert events[0]["data"]["playerId"] == "c" and NI.is_over(state)
    assert NI.next_deadline(state) is None
    assert NI.get_results(state) == [
        {"player_id": "b", "placement": 1, "score": 2},
        {"player_id": "c", "placement": 2, "score": 1},
        {"player_id": "a", "placement": 3, "score": 0},
    ]
    assert code_of(state, "b", {"type": "submitAnswer", "text": "Blue"}) == "INVALID_ACTION"


def test_view_shape_and_serializable() -> None:
    state, _ = answer(new(), "Apple")
    view = NI.get_view(state, "b")
    json.dumps(view)
    assert view["isYourTurn"] and view["currentPlayerId"] == "b" and view["topic"] == "Fruits"
    assert "normalized" not in json.dumps(view)
    assert set(view) == {
        "phase", "topic", "topicChooserId", "isTopicChooser", "suggestions", "topicDeadline",
        "order", "alive", "eliminated", "currentPlayerId", "isYourTurn", "turnDeadline",
        "pausedMs", "used", "challengeWindow", "challengeWindowMs", "canChallenge", "challenge",
        "lastElimination", "settings",
    }


def test_without_custom_topics_only_a_suggestion_is_accepted() -> None:
    state = new(topic=None, allowCustomTopics=False)
    others = [t for t in TOPICS if t not in state.suggestions]
    assert code_of(state, "a", {"type": "chooseTopic", "topic": others[0]}) == "INVALID_ACTION"
    assert code_of(state, "a", {"type": "chooseTopic", "topic": "Cheeses"}) == "INVALID_ACTION"
    pick = state.suggestions[2]
    state, _ = act(state, "a", {"type": "chooseTopic", "topic": f"  {pick} "})
    assert state.topic == pick and state.phase == "turn"


def test_suggestions_differ_between_topic_picks() -> None:
    state = new(topic=None, seed=3)
    first = list(state.suggestions)
    state, _ = act(state, "a", {"type": "chooseTopic", "topic": first[0]})
    state, _ = NI.tick(state, T0 + TURN)  # a times out and picks next
    assert len(state.suggestions) == NAMEIT_TOPIC_SUGGESTIONS and state.suggestions != first


@pytest.mark.parametrize("reason", ["quit", "left", "offline"])
def test_forfeit_on_your_turn_eliminates_and_passes_the_turn(reason) -> None:
    state, _ = answer(new(), "Apple", now=T0)  # b's turn
    state, events = NI.forfeit(state, "b", T0 + 2000, reason)
    assert events == [{"kind": "eliminated", "data": {
        "playerId": "b", "reason": "forfeit", "text": None, "topic": "Fruits",
    }}]
    assert state.alive == ["a", "c", "d"] and state.eliminated == ["b"]
    assert state.phase == "turn" and state.topic == "Fruits"  # no new topic
    assert state.current == "c" and state.turn_deadline == T0 + 2000 + TURN
    assert [u["text"] for u in state.used] == ["Apple"]


def test_three_players_continue_with_two_survivors() -> None:
    state = new(("a", "b", "c"))
    state, _ = NI.forfeit(state, "c", T0 + 1, "quit")
    assert not NI.is_over(state) and state.alive == ["a", "b"] and state.current == "a"
    state, _ = NI.forfeit(state, "b", T0 + 2, "quit")
    assert NI.is_over(state) and NI.get_results(state)[0]["player_id"] == "a"


def test_forfeiting_topic_chooser_gets_a_random_suggestion() -> None:
    state = new(topic=None)
    assert state.phase == "topicSelect" and state.chooser == "a" and state.starter == "a"
    state, _ = NI.forfeit(state, "a", T0 + 10, "offline")
    assert state.phase == "turn" and state.topic in state.suggestions
    assert state.current == "b" and state.turn_deadline == T0 + 10 + TURN


def test_eliminated_chooser_who_forfeits_still_gets_a_topic_picked() -> None:
    state, _ = NI.tick(new(), T0 + TURN)  # a times out and must pick the next topic
    assert state.phase == "topicSelect" and state.chooser == "a" and state.starter == "b"
    state, events = NI.forfeit(state, "a", T0 + TURN + 5, "left")
    assert events == [] and state.phase == "turn" and state.current == "b"
    assert state.eliminated == ["a"]  # no second elimination


def test_forfeit_of_the_answerer_cancels_the_challenge() -> None:
    state, _ = answer(new(), "Apple", now=T0)
    state, _ = challenge(state, by="c", now=T0 + 3000)
    state, events = NI.forfeit(state, "a", T0 + 4000, "quit")
    assert [e["kind"] for e in events] == ["eliminated"]
    assert state.phase == "turn" and state.challenge is None and state.current == "b"
    assert state.turn_deadline == T0 + 4000 + TURN - 3000


def test_forfeit_of_a_voter_recounts_the_vote() -> None:
    state, _ = answer(new(), "Banana")
    state, _ = challenge(state, by="b")
    state, _ = act(state, "c", {"type": "vote", "valid": False})
    state, events = NI.forfeit(state, "d", T0 + 2000, "quit")  # last voter gone: closes
    assert [e["kind"] for e in events] == ["eliminated", "challengeResult", "eliminated"]
    assert events[1]["data"]["valid"] is False and events[2]["data"]["playerId"] == "a"
    assert state.phase == "topicSelect" and state.chooser == "a" and state.starter == "b"


def test_forfeit_of_the_paused_player_hands_the_turn_on() -> None:
    state, _ = answer(new(), "Apple", now=T0)  # b to answer, then c challenges a
    state, _ = challenge(state, by="c", now=T0 + 3000)
    state, _ = NI.forfeit(state, "b", T0 + 3500, "quit")
    assert state.phase == "challenge" and state.current == "c" and state.paused_ms == TURN
    assert state.challenge["voters"] == ["d"]
    state, events = act(state, "d", {"type": "vote", "valid": True}, T0 + 4000)
    assert state.phase == "turn" and state.current == "c"
    assert state.turn_deadline == T0 + 4000 + TURN


def test_forfeiters_answer_can_no_longer_be_challenged() -> None:
    state, _ = answer(new(), "Apple", now=T0)
    state, _ = NI.forfeit(state, "a", T0 + 100, "quit")
    assert state.window_until is None and not NI.get_view(state, "c")["canChallenge"]
