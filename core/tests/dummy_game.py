"""A trivial test-only game proving the room loop: turns, a timer, a secret and results.

Rules: players take turns sending {"type": "score"}; first to `target` points wins.
A turn not taken within `turnMs` is skipped by `tick`. Only the first player's view
contains `secret`, so leak handling can be checked end to end. A forfeiting player leaves
the turn order; the game is over once only one player is left after a forfeit.
"""

import random
from typing import Any

from games.base import GameError, GameEvent, GameModule, GameResult

SECRET = "dummy-secret-xyz"


class DummyGame(GameModule):
    id = "dummy"
    name = "Dummy"
    min_players = 1
    max_players = 10
    default_settings: dict[str, Any] = {"target": 2, "turnMs": 10_000}

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = {**self.default_settings, **settings}
        if set(merged) != set(self.default_settings):
            raise GameError("INVALID_ACTION", "Unknown setting.")
        if not isinstance(merged["target"], int) or not 1 <= merged["target"] <= 10:
            raise GameError("INVALID_ACTION", "target must be 1..10.")
        return merged

    def init(self, players: list[str], settings: dict[str, Any], rng: random.Random, now: float):
        return {
            "order": list(players),
            "turn": 0,
            "scores": dict.fromkeys(players, 0),
            "target": settings["target"],
            "turnMs": settings["turnMs"],
            "deadline": now + settings["turnMs"],
            "offline": [],
            "forfeited": [],
        }

    def handle_action(self, state, player_id, action, now) -> tuple[Any, list[GameEvent]]:
        if action.get("type") != "score":
            raise GameError("INVALID_ACTION", "Unknown action.")
        if state["order"][state["turn"]] != player_id:
            raise GameError("NOT_YOUR_TURN", "Not your turn.")
        state["scores"][player_id] += 1
        self._advance(state, now)
        return state, [{"kind": "scored", "data": {"playerId": player_id}}]

    def tick(self, state, now) -> tuple[Any, list[GameEvent]]:
        if self.is_over(state) or now < state["deadline"]:
            return state, []
        skipped = state["order"][state["turn"]]
        self._advance(state, now)
        return state, [{"kind": "timeout", "data": {"playerId": skipped}}]

    def on_presence(self, state, player_id, online, now) -> tuple[Any, list[GameEvent]]:
        offline = set(state["offline"])
        (offline.discard if online else offline.add)(player_id)
        state["offline"] = sorted(offline)
        return state, []

    def forfeit(self, state, player_id, now, reason) -> tuple[Any, list[GameEvent]]:
        order = state["order"]
        index, current = order.index(player_id), order[state["turn"]]
        order.remove(player_id)
        state["forfeited"].append(player_id)
        if order:
            if current == player_id:
                state["turn"], state["deadline"] = index % len(order), now + state["turnMs"]
            else:
                state["turn"] = order.index(current)
        return state, [{"kind": "forfeit", "data": {"playerId": player_id, "reason": reason}}]

    def get_view(self, state, player_id) -> dict[str, Any]:
        view = {
            "turn": state["order"][state["turn"]],
            "scores": dict(state["scores"]),
            "deadline": state["deadline"],
            "offline": list(state["offline"]),
        }
        if player_id == state["order"][0]:
            view["secret"] = SECRET
        return view

    def next_deadline(self, state) -> float | None:
        return None if self.is_over(state) else state["deadline"]

    def is_over(self, state) -> bool:
        if state["forfeited"] and len(state["order"]) <= 1:
            return True
        return max(state["scores"].values()) >= state["target"]

    def get_results(self, state) -> list[GameResult]:
        ranked = sorted(set(state["scores"].values()), reverse=True)
        return [
            {"player_id": pid, "placement": ranked.index(pts) + 1, "score": pts}
            for pid, pts in state["scores"].items()
        ]

    @staticmethod
    def _advance(state: dict[str, Any], now: float) -> None:
        state["turn"] = (state["turn"] + 1) % len(state["order"])
        state["deadline"] = now + state["turnMs"]
