"""Game module base class and registry."""

import random
from typing import Any

import pytest

from games import registry
from games.base import GameError, GameEvent, GameModule, GameResult


class _Tiny(GameModule):
    """Smallest complete module, only to check the contract is implementable."""

    id = "tiny_test"
    name = "Tiny"
    min_players = 1
    max_players = 2
    default_settings: dict[str, Any] = {}

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        return {**self.default_settings, **settings}

    def init(self, players: list[str], settings: dict[str, Any], rng: random.Random, now: float):
        return {"players": players}

    def handle_action(self, state, player_id, action, now) -> tuple[Any, list[GameEvent]]:
        raise GameError("INVALID_ACTION", "nope")

    def tick(self, state, now) -> tuple[Any, list[GameEvent]]:
        return state, []

    def get_view(self, state, player_id) -> dict[str, Any]:
        return {}

    def next_deadline(self, state) -> float | None:
        return None

    def is_over(self, state) -> bool:
        return True

    def get_results(self, state) -> list[GameResult]:
        return [{"player_id": p, "placement": 1, "points": 0} for p in state["players"]]


def test_base_is_abstract() -> None:
    with pytest.raises(TypeError):
        GameModule()  # type: ignore[abstract]


def test_game_error_carries_code_and_message() -> None:
    err = GameError("NOT_YOUR_TURN", "Wait for your turn.")
    assert err.code == "NOT_YOUR_TURN"
    assert err.message == str(err) == "Wait for your turn."


def test_registry_register_get_unregister() -> None:
    tiny = _Tiny()
    registry.register(tiny)
    try:
        assert registry.get_game("tiny_test") is tiny
        assert "tiny_test" in registry.all_games()
    finally:
        registry.unregister("tiny_test")
    assert registry.get_game("tiny_test") is None


def test_unknown_game_is_none() -> None:
    assert registry.get_game("chess") is None


def test_game_ids_are_fixed() -> None:
    assert registry.GAME_IDS == (
        "rps", "guess_race", "hangman", "dots_and_boxes", "liars_dice", "name_it",
    )


def test_on_presence_defaults_to_no_change() -> None:
    state = {"players": ["a"]}
    assert _Tiny().on_presence(state, "a", False, 0.0) == (state, [])
