"""Maps game ids to module instances. Modules are added here as each phase lands."""

from games.base import GameModule

GAME_IDS: tuple[str, ...] = (
    "rps",
    "guess_race",
    "hangman",
    "dots_and_boxes",
    "liars_dice",
    "name_it",
)

_REGISTRY: dict[str, GameModule] = {}


def register(module: GameModule) -> None:
    """Add a module under its id. Re-registering the same id replaces it (used by tests)."""
    _REGISTRY[module.id] = module


def unregister(game_id: str) -> None:
    """Remove a module if present (used by tests to clean up test-only games)."""
    _REGISTRY.pop(game_id, None)


def get_game(game_id: str) -> GameModule | None:
    """Return the module for `game_id`, or None if unknown."""
    return _REGISTRY.get(game_id)


def all_games() -> dict[str, GameModule]:
    """A copy of the registry, keyed by game id."""
    return dict(_REGISTRY)


def _register_builtin() -> None:
    """Register the shipped game modules."""
    from games.dots_and_boxes import DotsAndBoxes
    from games.guess_race import GuessRace
    from games.hangman import Hangman
    from games.liars_dice import LiarsDice
    from games.name_it import NameIt
    from games.rps import RockPaperScissors

    register(RockPaperScissors())
    register(GuessRace())
    register(Hangman())
    register(DotsAndBoxes())
    register(LiarsDice())
    register(NameIt())


_register_builtin()
