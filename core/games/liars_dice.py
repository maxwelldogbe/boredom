"""Liar's Dice (plan section 11): bid on everyone's hidden dice, call Liar, last one standing wins.

A bid beats the current one with a higher quantity, or the same quantity and a higher face.
On Liar, all dice are revealed: if the actual count reaches the bid the caller loses a die,
else the bidder does. With spot-on enabled, an exact count gains the caller a die (up to
startingDice), otherwise the caller loses one. A random player opens the first round;
the loser starts each later one.

A forfeiting player is eliminated and their dice leave the table. That can change whether
the standing bid is true, so a round still being bid is voided: everyone re-rolls, the bid
is cleared, nobody loses a die, and the next alive player after the forfeiter starts.
"""

import random
from dataclasses import dataclass, field
from typing import Any

from games.base import ForfeitReason, GameError, GameEvent, GameModule, GameResult
from games.constants import DICE_REVEAL_MS, DICE_TURN_MS

FACES = range(1, 7)


@dataclass
class DiceState:
    order: list[str]
    settings: dict[str, Any]
    rng: random.Random
    dice: dict[str, list[int]] = field(default_factory=dict)  # secret until a reveal
    counts: dict[str, int] = field(default_factory=dict)
    eliminated: list[str] = field(default_factory=list)  # in elimination order
    round: int = 0
    turn: str = ""
    bid: dict[str, Any] | None = None  # {playerId, quantity, face}
    history: list[dict[str, Any]] = field(default_factory=list)
    phase: str = "bidding"  # bidding | reveal | done
    deadline: float | None = None  # turn deadline (bidding) or reveal end (reveal)
    last_reveal: dict[str, Any] | None = None
    next_starter: str = ""

    def alive(self) -> list[str]:
        return [p for p in self.order if self.counts[p] > 0]

    def total_dice(self) -> int:
        return sum(self.counts.values())

    def next_alive(self, player_id: str) -> str:
        """The first alive player after `player_id` in seat order (wrapping)."""
        i = self.order.index(player_id)
        for step in range(1, len(self.order) + 1):
            candidate = self.order[(i + step) % len(self.order)]
            if self.counts[candidate] > 0:
                return candidate
        return player_id


def count_face(dice: dict[str, list[int]], face: int, wild_ones: bool) -> int:
    """How many dice show `face`; with wild ones, ones also count unless the bid is on ones."""
    wild = wild_ones and face != 1
    return sum(1 for hand in dice.values() for d in hand if d == face or (wild and d == 1))


def beats(quantity: int, face: int, bid: dict[str, Any] | None) -> bool:
    """True if (quantity, face) is a legal raise over `bid`."""
    if bid is None:
        return True
    return quantity > bid["quantity"] or (quantity == bid["quantity"] and face > bid["face"])


def minimum_raise(bid: dict[str, Any] | None) -> tuple[int, int]:
    """The smallest legal bid after `bid`."""
    if bid is None:
        return 1, 1
    if bid["face"] < 6:
        return bid["quantity"], bid["face"] + 1
    return bid["quantity"] + 1, 1


def compute_scores(state: DiceState) -> dict[str, int]:
    """Display score: players outlasted (n - placement). The only scoring rule here."""
    n = len(state.order)
    return {p: n - place for p, place in placements(state).items()}


def placements(state: DiceState) -> dict[str, int]:
    """Survivor 1st, then in reverse elimination order (first out is last)."""
    alive = state.alive()
    ranking = alive + list(reversed(state.eliminated))
    return {p: i + 1 for i, p in enumerate(ranking)}


class LiarsDice(GameModule):
    id = "liars_dice"
    name = "Liar's Dice"
    min_players = 2
    max_players = 6
    default_settings: dict[str, Any] = {"startingDice": 5, "wildOnes": False, "spotOn": False}

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = {**self.default_settings, **settings}
        if set(merged) != set(self.default_settings):
            raise GameError("INVALID_ACTION", "Unknown setting.")
        dice = merged["startingDice"]
        if not isinstance(dice, int) or isinstance(dice, bool) or not 3 <= dice <= 6:
            raise GameError("INVALID_ACTION", "startingDice must be 3 to 6.")
        for key in ("wildOnes", "spotOn"):
            if not isinstance(merged[key], bool):
                raise GameError("INVALID_ACTION", f"{key} must be true or false.")
        return merged

    def init(self, players: list[str], settings: dict[str, Any], rng: random.Random, now: float):
        state = DiceState(order=list(players), settings=dict(settings), rng=rng)
        state.counts = dict.fromkeys(players, settings["startingDice"])
        self._new_round(state, rng.choice(players), now)  # random first starter
        return state

    def _new_round(self, state: DiceState, starter: str, now: float) -> None:
        state.round += 1
        state.dice = {
            p: sorted(state.rng.randint(1, 6) for _ in range(state.counts[p])) for p in state.order
        }
        state.turn, state.bid, state.history = starter, None, []
        state.phase, state.deadline, state.last_reveal = "bidding", now + DICE_TURN_MS, None

    # ----- actions -------------------------------------------------------------------------

    def handle_action(self, state: DiceState, player_id, action, now) -> tuple[Any, list]:
        kind = action.get("type")
        if kind not in ("bid", "callLiar", "callSpotOn"):
            raise GameError("INVALID_ACTION", "Unknown action.")
        if state.phase != "bidding":
            raise GameError("INVALID_ACTION", "Wait for the next round.")
        if player_id != state.turn:
            raise GameError("NOT_YOUR_TURN", "Wait for your turn.")
        if kind == "bid":
            quantity, face = action.get("quantity"), action.get("face")
            for value in (quantity, face):
                if not isinstance(value, int) or isinstance(value, bool):
                    raise GameError("INVALID_ACTION", "Bid a whole quantity and a face.")
            if face not in FACES or not 1 <= quantity <= state.total_dice():
                raise GameError(
                    "INVALID_ACTION", f"Bid 1 to {state.total_dice()} dice showing 1 to 6."
                )
            if not beats(quantity, face, state.bid):
                raise GameError(
                    "INVALID_ACTION", "Raise the quantity, or keep it and raise the face."
                )
            self._bid(state, quantity, face, now, auto=False)
            return state, []
        if state.bid is None:
            raise GameError("INVALID_ACTION", "The first move of a round must be a bid.")
        if kind == "callSpotOn" and not state.settings["spotOn"]:
            raise GameError("INVALID_ACTION", "Spot-on is turned off for this game.")
        call = "liar" if kind == "callLiar" else "spotOn"
        return state, [self._challenge(state, call, now, auto=False)]

    def _bid(self, state: DiceState, quantity: int, face: int, now: float, auto: bool) -> None:
        state.bid = {"playerId": state.turn, "quantity": quantity, "face": face}
        state.history.append({**state.bid, "auto": auto})
        state.turn = state.next_alive(state.turn)
        state.deadline = now + DICE_TURN_MS

    def _challenge(self, state: DiceState, call: str, now: float, auto: bool) -> GameEvent:
        assert state.bid is not None
        caller, bidder = state.turn, state.bid["playerId"]
        actual = count_face(state.dice, state.bid["face"], state.settings["wildOnes"])
        loser = gainer = None
        if call == "liar":
            loser = caller if actual >= state.bid["quantity"] else bidder
        elif actual == state.bid["quantity"]:
            gainer = caller
            state.counts[caller] = min(state.counts[caller] + 1, state.settings["startingDice"])
        else:
            loser = caller
        eliminated = None
        if loser is not None:
            state.counts[loser] -= 1
            if state.counts[loser] == 0:
                eliminated = loser
                state.eliminated.append(loser)
        starter = loser or gainer or caller
        state.next_starter = starter if state.counts[starter] > 0 else state.next_alive(starter)
        state.last_reveal = {
            "round": state.round,
            "call": call,
            "callerId": caller,
            "bid": dict(state.bid),
            "dice": {p: list(hand) for p, hand in state.dice.items() if hand},
            "actual": actual,
            "loserId": loser,
            "gainerId": gainer,
            "eliminatedId": eliminated,
            "auto": auto,
        }
        state.phase, state.deadline = "reveal", now + DICE_REVEAL_MS
        return {"kind": "reveal", "data": dict(state.last_reveal)}

    # ----- timers ------------------------------------------------------------------------------

    def tick(self, state: DiceState, now) -> tuple[Any, list[GameEvent]]:
        if state.deadline is None or now < state.deadline:
            return state, []
        if state.phase == "reveal":
            if len(state.alive()) <= 1:
                state.phase, state.deadline, state.last_reveal = "done", None, None
            else:
                self._new_round(state, state.next_starter, now)
            return state, []
        quantity, face = minimum_raise(state.bid)
        if quantity <= state.total_dice():
            self._bid(state, quantity, face, now, auto=True)
            return state, []
        return state, [self._challenge(state, "liar", now, auto=True)]

    def next_deadline(self, state: DiceState) -> float | None:
        return state.deadline

    def forfeit(
        self, state: DiceState, player_id: str, now: float, reason: ForfeitReason
    ) -> tuple[Any, list[GameEvent]]:
        if state.phase == "done" or state.counts.get(player_id, 0) == 0:
            return state, []
        state.counts[player_id] = 0
        state.dice[player_id] = []
        state.eliminated.append(player_id)
        starter = state.next_alive(player_id)
        if len(state.alive()) <= 1:
            state.phase, state.deadline, state.last_reveal = "done", None, None
            return state, []
        if state.phase == "reveal":  # the round is already settled; just fix who starts
            if state.next_starter == player_id:
                state.next_starter = starter
            return state, []
        voided = state.round
        self._new_round(state, starter, now)
        event: GameEvent = {
            "kind": "roundVoided",
            "data": {"round": voided, "playerId": player_id, "starterId": starter},
        }
        return state, [event]

    # ----- views and results -------------------------------------------------------------------

    def get_view(self, state: DiceState, player_id: str) -> dict[str, Any]:
        bidding = state.phase == "bidding"
        return {
            "phase": state.phase,
            "round": state.round,
            "order": list(state.order),
            "myDice": list(state.dice.get(player_id, [])),
            "diceCounts": dict(state.counts),
            "totalDice": state.total_dice(),
            "eliminated": list(state.eliminated),
            "currentPlayerId": state.turn if bidding else None,
            "isYourTurn": bidding and player_id == state.turn,
            "currentBid": dict(state.bid) if state.bid else None,
            "history": [dict(h) for h in state.history],
            "settings": dict(state.settings),
            "deadline": state.deadline,
            "lastReveal": state.last_reveal if state.phase == "reveal" else None,
        }

    def is_over(self, state: DiceState) -> bool:
        return state.phase == "done"

    def get_results(self, state: DiceState) -> list[GameResult]:
        places, scores = placements(state), compute_scores(state)
        ranked = sorted(places, key=lambda p: places[p])
        return [{"player_id": p, "placement": places[p], "score": scores[p]} for p in ranked]
