"""Liar's Dice module: pure calls with injected time."""

import json
import random

import pytest

from games import registry
from games.base import GameError
from games.constants import DICE_REVEAL_MS, DICE_TURN_MS
from games.liars_dice import LiarsDice, beats, count_face, minimum_raise

LD = LiarsDice()
T0 = 4_000_000.0


def new(players=("a", "b", "c"), seed=1, **settings):
    state = LD.init(list(players), LD.validate_settings(settings), random.Random(seed), T0)
    state.turn = players[0]  # scripted turns assume a opens; the random opener is tested below
    return state


def test_first_round_opener_is_random() -> None:
    openers = {
        LD.init(["a", "b", "c"], LD.validate_settings({}), random.Random(s), T0).turn
        for s in range(30)
    }
    assert openers == {"a", "b", "c"}


def act(state, action, pid=None, now=T0):
    return LD.handle_action(state, pid or state.turn, action, now)


def bid(state, quantity, face, pid=None, now=T0):
    return act(state, {"type": "bid", "quantity": quantity, "face": face}, pid, now)[0]


def code_of(state, action, pid=None):
    with pytest.raises(GameError) as exc:
        act(state, action, pid)
    return exc.value.code


def rig(state, **hands):
    """Replace the secret dice (and counts) for a scripted round."""
    for pid, hand in hands.items():
        state.dice[pid] = list(hand)
        state.counts[pid] = len(hand)
    return state


def test_registered_and_settings() -> None:
    assert isinstance(registry.get_game("liars_dice"), LiarsDice)
    assert LD.validate_settings({}) == {"startingDice": 5, "wildOnes": False, "spotOn": False}
    for bad in ({"startingDice": 2}, {"startingDice": 7}, {"startingDice": True},
                {"wildOnes": 1}, {"spotOn": "yes"}, {"jokers": True}):
        with pytest.raises(GameError):
            LD.validate_settings(bad)
    assert (LD.min_players, LD.max_players) == (2, 6)


def test_init_deals_starting_dice() -> None:
    state = new(startingDice=4)
    assert state.round == 1 and state.bid is None
    assert all(len(h) == 4 and all(1 <= d <= 6 for d in h) for h in state.dice.values())
    assert state.deadline == T0 + DICE_TURN_MS


@pytest.mark.parametrize(
    ("quantity", "face", "ok"),
    [(3, 4, True), (2, 5, True), (2, 6, True), (2, 4, False), (2, 3, False), (1, 6, False)],
)
def test_bid_ordering(quantity, face, ok) -> None:
    current = {"playerId": "a", "quantity": 2, "face": 4}
    assert beats(quantity, face, current) is ok
    state = bid(new(), 2, 4)
    if ok:
        assert bid(state, quantity, face).bid["quantity"] == quantity
    else:
        action = {"type": "bid", "quantity": quantity, "face": face}
        assert code_of(state, action) == "INVALID_ACTION"


@pytest.mark.parametrize(
    "action",
    [
        {"type": "bid", "quantity": 0, "face": 3},
        {"type": "bid", "quantity": 16, "face": 3},  # more than the 15 dice in play
        {"type": "bid", "quantity": 2, "face": 7},
        {"type": "bid", "quantity": 2, "face": 0},
        {"type": "bid", "quantity": "2", "face": 3},
        {"type": "bid", "quantity": True, "face": 3},
        {"type": "bid", "quantity": 2},
        {"type": "callLiar"},  # nothing to challenge yet
        {"type": "callSpotOn"},
        {"type": "fold"},
    ],
)
def test_invalid_actions(action) -> None:
    assert code_of(new(spotOn=True), action) == "INVALID_ACTION"


def test_out_of_turn_and_spot_on_disabled() -> None:
    state = bid(new(), 1, 2)
    assert code_of(state, {"type": "callLiar"}, pid="a") == "NOT_YOUR_TURN"
    assert code_of(state, {"type": "callSpotOn"}) == "INVALID_ACTION"


def test_wild_ones_count_unless_bid_on_ones() -> None:
    dice = {"a": [1, 1, 3], "b": [3, 5, 1]}
    assert count_face(dice, 3, wild_ones=False) == 2
    assert count_face(dice, 3, wild_ones=True) == 5
    assert count_face(dice, 1, wild_ones=True) == 3
    assert count_face(dice, 6, wild_ones=True) == 3


def test_liar_wrong_caller_loses_a_die() -> None:
    state = rig(new(), a=[3, 3, 1, 2, 6], b=[3, 4, 4, 5, 5], c=[2, 2, 2, 2, 2])
    state = bid(state, 3, 3)
    state, events = act(state, {"type": "callLiar"}, now=T0 + 10)
    reveal = events[0]["data"]
    assert events[0]["kind"] == "reveal"
    assert reveal["actual"] == 3 and reveal["loserId"] == "b" and reveal["callerId"] == "b"
    assert reveal["dice"]["c"] == [2, 2, 2, 2, 2] and reveal["call"] == "liar"
    assert state.counts["b"] == 4 and state.phase == "reveal"
    assert state.deadline == T0 + 10 + DICE_REVEAL_MS


def test_liar_right_bidder_loses_and_starts_next_round() -> None:
    state = rig(new(wildOnes=True), a=[3, 1, 2, 2, 6], b=[4, 4, 4, 5, 5], c=[2, 2, 2, 2, 2])
    state = bid(state, 4, 3)  # 3s: one 3 + one wild 1 = 2
    state, events = act(state, {"type": "callLiar"})
    assert events[0]["data"]["actual"] == 2 and events[0]["data"]["loserId"] == "a"
    state, _ = LD.tick(state, T0 + DICE_REVEAL_MS)
    assert state.phase == "bidding" and state.round == 2 and state.turn == "a"
    assert len(state.dice["a"]) == 4 and state.bid is None and state.history == []


def test_spot_on_exact_gains_up_to_starting_dice_otherwise_loses() -> None:
    state = rig(new(spotOn=True), a=[6, 6, 1, 2], b=[6, 4, 4, 5, 5], c=[2, 2, 2, 2, 2])
    state = bid(state, 3, 6)
    state, events = act(state, {"type": "callSpotOn"})
    assert events[0]["data"]["gainerId"] == "b" and events[0]["data"]["loserId"] is None
    assert state.counts["b"] == 5  # already at the maximum
    state, _ = LD.tick(state, T0 + DICE_REVEAL_MS)
    assert state.turn == "b"
    rig(state, a=[6, 6, 1, 2], b=[6, 4, 4, 5], c=[2, 2, 2, 2, 2])
    state.turn = "a"
    state = bid(state, 3, 6)
    state.counts["b"] = 3
    state.dice["b"] = [6, 6, 1]
    state, events = act(state, {"type": "callSpotOn"})
    assert events[0]["data"]["gainerId"] is None and events[0]["data"]["loserId"] == "b"
    assert state.counts["b"] == 2


def test_elimination_next_alive_starts_and_placement_by_elimination() -> None:
    state = rig(new(), a=[2], b=[5, 5], c=[6, 6])
    state = bid(state, 1, 4)  # a bids one 4: there are none
    state, events = act(state, {"type": "callLiar"})
    assert events[0]["data"]["eliminatedId"] == "a" and state.eliminated == ["a"]
    state, _ = LD.tick(state, T0 + DICE_REVEAL_MS)
    assert state.turn == "b" and state.dice["a"] == [] and LD.get_view(state, "a")["myDice"] == []
    assert state.next_alive("c") == "b"
    rig(state, b=[5], c=[6, 6])
    state = bid(state, 1, 6)  # b bids one 6: true
    state, events = act(state, {"type": "callLiar"})  # c is wrong and loses one
    assert events[0]["data"]["loserId"] == "c"
    state, _ = LD.tick(state, T0 + DICE_REVEAL_MS)
    assert state.turn == "c"
    rig(state, b=[5], c=[6])
    state = bid(state, 1, 6)  # c bids one 6: true
    state, events = act(state, {"type": "callLiar"})  # b is wrong with one die left: out
    assert events[0]["data"]["eliminatedId"] == "b"
    assert not LD.is_over(state)
    state, _ = LD.tick(state, T0 + DICE_REVEAL_MS)
    assert LD.is_over(state) and LD.next_deadline(state) is None
    assert LD.get_results(state) == [
        {"player_id": "c", "placement": 1, "score": 2},
        {"player_id": "b", "placement": 2, "score": 1},
        {"player_id": "a", "placement": 3, "score": 0},
    ]


def test_minimum_raise() -> None:
    assert minimum_raise(None) == (1, 1)
    assert minimum_raise({"quantity": 2, "face": 3}) == (2, 4)
    assert minimum_raise({"quantity": 2, "face": 6}) == (3, 1)


def test_timeout_makes_minimum_raise_then_calls_liar_when_none_possible() -> None:
    state = new(("a", "b"), startingDice=3)
    state, _ = LD.tick(state, T0 + DICE_TURN_MS - 1)
    assert state.bid is None
    state, _ = LD.tick(state, T0 + DICE_TURN_MS)
    assert state.bid == {"playerId": "a", "quantity": 1, "face": 1}
    assert state.history[-1]["auto"] is True and state.turn == "b"
    assert state.deadline == T0 + 2 * DICE_TURN_MS
    state = bid(state, 6, 6)  # the maximum: 6 dice in play
    state, events = LD.tick(state, state.deadline)
    assert events[0]["kind"] == "reveal" and events[0]["data"]["auto"] is True
    assert events[0]["data"]["callerId"] == "a" and events[0]["data"]["call"] == "liar"


def test_views_never_show_opponent_dice_outside_reveal() -> None:
    state = rig(new(), a=[1, 2, 3, 4, 5], b=[6, 6, 6, 6, 6], c=[2, 2, 3, 3, 4])
    state = bid(state, 2, 2)
    view = LD.get_view(state, "a")
    assert view["myDice"] == [1, 2, 3, 4, 5] and view["lastReveal"] is None
    assert view["diceCounts"] == {"a": 5, "b": 5, "c": 5} and view["totalDice"] == 15
    assert "6, 6, 6" not in json.dumps(view) and "[6, 6" not in json.dumps(view)
    for pid in "abc":
        blob = json.dumps({k: v for k, v in LD.get_view(state, pid).items() if k != "myDice"})
        assert "dice\": [" not in blob
    state, _ = act(state, {"type": "callLiar"})
    revealed = LD.get_view(state, "a")["lastReveal"]
    assert revealed["dice"]["b"] == [6, 6, 6, 6, 6]
    state, _ = LD.tick(state, T0 + DICE_REVEAL_MS)
    assert LD.get_view(state, "a")["lastReveal"] is None


def test_view_shape_and_turn_flags() -> None:
    state = bid(new(), 2, 3)
    view = LD.get_view(state, "b")
    json.dumps(view)
    assert view["isYourTurn"] and view["currentPlayerId"] == "b"
    assert view["currentBid"] == {"playerId": "a", "quantity": 2, "face": 3}
    assert view["history"] == [{"playerId": "a", "quantity": 2, "face": 3, "auto": False}]
    assert set(view) == {
        "phase", "round", "order", "myDice", "diceCounts", "totalDice", "eliminated",
        "currentPlayerId", "isYourTurn", "currentBid", "history", "settings", "deadline",
        "lastReveal",
    }
    assert not LD.get_view(state, "a")["isYourTurn"]


def test_same_seed_same_dice() -> None:
    assert new(seed=9).dice == new(seed=9).dice


@pytest.mark.parametrize("reason", ["quit", "left", "offline"])
def test_forfeit_voids_the_round_and_everyone_rerolls(reason) -> None:
    state = rig(new(("a", "b", "c", "d")), a=[2, 2, 2], b=[5, 5], c=[2, 6, 6, 6], d=[1, 1, 3])
    state = bid(state, 3, 2)  # true only with c's twos
    state = bid(state, 4, 2)
    assert state.turn == "c"
    state, events = LD.forfeit(state, "b", T0 + 100, reason)
    voided = {"round": 1, "playerId": "b", "starterId": "c"}
    assert events == [{"kind": "roundVoided", "data": voided}]
    assert state.round == 2 and state.bid is None and state.history == []
    assert state.counts == {"a": 3, "b": 0, "c": 4, "d": 3} and state.eliminated == ["b"]
    assert [len(state.dice[p]) for p in "abcd"] == [3, 0, 4, 3]
    assert state.turn == "c" and state.deadline == T0 + 100 + DICE_TURN_MS
    assert LD.get_view(state, "a")["totalDice"] == 10
    for viewer in "abcd":  # each view holds only the viewer's own new dice
        view = LD.get_view(state, viewer)
        assert view["myDice"] == state.dice[viewer] and view["lastReveal"] is None


def test_forfeit_of_the_player_to_move_passes_the_start_on() -> None:
    state = bid(new(("a", "b", "c")), 1, 2)
    assert state.turn == "b"
    state, _ = LD.forfeit(state, "b", T0 + 1, "quit")
    assert state.turn == "c" and state.bid is None


def test_forfeit_during_a_reveal_keeps_the_result() -> None:
    state = rig(new(("a", "b", "c")), a=[3, 3], b=[4, 4], c=[5, 5])
    state = bid(state, 3, 3)
    state, _ = act(state, {"type": "callLiar"})  # b calls, a loses a die and starts next
    assert state.phase == "reveal" and state.next_starter == "a"
    state, events = LD.forfeit(state, "a", T0 + 1, "left")
    assert events == [] and state.phase == "reveal" and state.next_starter == "b"
    assert state.counts["a"] == 0 and state.last_reveal["loserId"] == "a"
    state, _ = LD.tick(state, state.deadline)
    assert state.round == 2 and state.turn == "b" and state.counts == {"a": 0, "b": 2, "c": 2}


def test_forfeit_down_to_one_player_ends_the_game() -> None:
    state, _ = LD.forfeit(new(("a", "b")), "a", T0, "quit")
    assert LD.is_over(state) and LD.get_results(state)[0]["player_id"] == "b"


def test_forfeit_after_elimination_changes_nothing() -> None:
    state, _ = LD.forfeit(new(("a", "b", "c")), "c", T0, "quit")
    snapshot = (dict(state.counts), list(state.eliminated), state.round)
    state, events = LD.forfeit(state, "c", T0 + 1, "offline")
    assert events == [] and (state.counts, state.eliminated, state.round) == snapshot
