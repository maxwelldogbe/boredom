"""Central placement scoring (games/scoring.py)."""

import pytest

from games import scoring
from games.base import competition_placements
from games.constants import SESSION_POINTS_MAX
from games.scoring import placement_points, score_results

M = SESSION_POINTS_MAX


def test_session_points_max_is_100() -> None:
    assert M == 100


def test_two_players() -> None:
    assert placement_points({"a": 1, "b": 2}, M) == {"a": 100, "b": 0}


def test_three_players() -> None:
    assert placement_points({"a": 1, "b": 2, "c": 3}, M) == {"a": 100, "b": 50, "c": 0}


def test_four_players() -> None:
    assert placement_points({"a": 1, "b": 2, "c": 3, "d": 4}, M) == {
        "a": 100, "b": 66.67, "c": 33.33, "d": 0,
    }


def test_ten_players_are_evenly_spaced() -> None:
    placements = {f"p{i}": i for i in range(1, 11)}
    points = placement_points(placements, M)
    assert points["p1"] == 100 and points["p10"] == 0
    assert points["p2"] == 88.89 and points["p5"] == 55.56 and points["p9"] == 11.11
    assert all(points[f"p{i}"] > points[f"p{i + 1}"] for i in range(1, 10))


def test_two_tied_for_first_of_four_share_the_average_of_100_and_67() -> None:
    points = placement_points({"a": 1, "b": 1, "c": 3, "d": 4}, M)
    assert points == {"a": 83.33, "b": 83.33, "c": 33.33, "d": 0}


@pytest.mark.parametrize(
    ("placements", "expected"),
    [
        ({"a": 1, "b": 2, "c": 2, "d": 4}, {"a": 100, "b": 50, "c": 50, "d": 0}),
        ({"a": 1, "b": 2, "c": 3, "d": 3}, {"a": 100, "b": 66.67, "c": 16.67, "d": 16.67}),
        ({"a": 1, "b": 1, "c": 1, "d": 4}, {"a": 66.67, "b": 66.67, "c": 66.67, "d": 0}),
        ({"a": 1, "b": 2, "c": 2, "d": 2}, {"a": 100, "b": 33.33, "c": 33.33, "d": 33.33}),
        ({"a": 1, "b": 1, "c": 3, "d": 3}, {"a": 83.33, "b": 83.33, "c": 16.67, "d": 16.67}),
        ({"a": 1, "b": 1}, {"a": 50, "b": 50}),
        ({"a": 1, "b": 2, "c": 2}, {"a": 100, "b": 25, "c": 25}),
    ],
)
def test_ties_at_every_position(placements, expected) -> None:
    assert placement_points(placements, M) == expected


@pytest.mark.parametrize("n", [2, 3, 4, 7, 10])
def test_all_tied_get_the_mean(n) -> None:
    points = placement_points({f"p{i}": 1 for i in range(n)}, M)
    assert set(points.values()) == {50.0}


@pytest.mark.parametrize("n", [2, 3, 4, 5, 6, 9, 10])
def test_total_is_always_n_times_half_max_ties_or_not(n) -> None:
    """Ties redistribute points but never create or destroy any."""
    untied = placement_points({f"p{i}": i + 1 for i in range(n)}, M)
    assert sum(untied.values()) == pytest.approx(n * M / 2, abs=0.01 * n)
    values = {f"p{i}": float(i // 2) for i in range(n)}  # pairs tie
    tied = placement_points(competition_placements(values), M)
    assert sum(tied.values()) == pytest.approx(n * M / 2, abs=0.01 * n)


def test_single_player_gets_max() -> None:
    assert placement_points({"solo": 1}, M) == {"solo": 100}


def test_no_players() -> None:
    assert placement_points({}, M) == {}


def test_rounded_to_two_decimals_and_other_max() -> None:
    assert placement_points({"a": 1, "b": 2, "c": 3, "d": 4}, 10) == {
        "a": 10, "b": 6.67, "c": 3.33, "d": 0,
    }


def test_score_results_keeps_order_and_adds_points() -> None:
    results = [
        {"player_id": "x", "placement": 1, "score": 7},
        {"player_id": "y", "placement": 2, "score": 3},
        {"player_id": "z", "placement": 2, "score": 3},
    ]
    assert score_results(results, M) == [
        {"player_id": "x", "placement": 1, "score": 7, "points": 100},
        {"player_id": "y", "placement": 2, "score": 3, "points": 25},
        {"player_id": "z", "placement": 2, "score": 3, "points": 25},
    ]


def test_module_is_pure() -> None:
    source = open(scoring.__file__, encoding="utf-8").read()
    for banned in ("django", "asyncio", "time.", "random"):
        assert banned not in source


def _rows(placements: dict[str, int]) -> list:
    return [{"player_id": p, "placement": n, "score": 10 - n} for p, n in placements.items()]


def test_forfeiters_rank_below_everyone_who_stayed_whatever_their_score() -> None:
    results = _rows({"a": 1, "b": 2, "c": 3, "d": 4})
    ranked = scoring.rank_with_forfeits(results, {"a": 5.0, "b": 9.0}, ["a", "b", "c", "d"])
    assert [(r["player_id"], r["placement"]) for r in ranked] == [
        ("c", 1), ("d", 2), ("b", 3), ("a", 4),
    ]
    assert {r["player_id"]: r["score"] for r in ranked}["a"] == 9  # raw score kept
    points = {r["player_id"]: r["points"] for r in score_results(ranked, M)}
    assert points == {"c": 100, "d": 66.67, "b": 33.33, "a": 0}


def test_stayers_keep_ties_and_simultaneous_forfeits_share_a_placement() -> None:
    results = _rows({"a": 1, "b": 1, "c": 3, "d": 4, "e": 5})
    ranked = scoring.rank_with_forfeits(results, {"d": 7.0, "e": 7.0}, list("abcde"))
    assert {r["player_id"]: r["placement"] for r in ranked} == {
        "a": 1, "b": 1, "c": 3, "d": 4, "e": 4,
    }


def test_players_missing_from_the_game_results_still_get_a_row() -> None:
    ranked = scoring.rank_with_forfeits(_rows({"a": 1}), {"b": 1.0}, ["a", "b"])
    assert ranked == [
        {"player_id": "a", "placement": 1, "score": 9},
        {"player_id": "b", "placement": 2, "score": 0},
    ]


def test_no_forfeits_changes_nothing() -> None:
    results = _rows({"a": 1, "b": 2, "c": 2})
    assert scoring.rank_with_forfeits(results, {}, ["a", "b", "c"]) == results
