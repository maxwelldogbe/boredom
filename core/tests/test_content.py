"""Content files: shipped files are valid, and the validators reject broken entries."""

import pytest

from games.content import (
    EMOJI,
    TOPICS,
    WORDS,
    ContentError,
    parse_emoji,
    parse_topics,
    parse_words,
)
from games.normalize import normalize


def test_shipped_content_sizes() -> None:
    assert len(WORDS) == 200 and len(EMOJI) == 100 and len(TOPICS) == 50


def test_words_have_lengths_and_difficulties() -> None:
    assert all(4 <= len(w.word) <= 9 for w in WORDS)
    assert {w.difficulty for w in WORDS} == {"easy", "medium", "hard"}


def test_emoji_answers_unique_after_normalizing() -> None:
    assert len({normalize(p.answer) for p in EMOJI}) == 100


def good_words(n=15):
    return [
        {"word": w, "difficulty": d}
        for d in ("easy", "medium", "hard")
        for w in (f"wor{chr(97 + i)}{d[:2]}" for i in range(n))
    ]


def test_valid_minimal_words() -> None:
    assert len(parse_words(good_words())) == 45


@pytest.mark.parametrize(
    "bad",
    [
        {"word": "abc", "difficulty": "easy"},
        {"word": "abcdefghij", "difficulty": "easy"},
        {"word": "Apple", "difficulty": "easy"},
        {"word": "ap ple", "difficulty": "easy"},
        {"word": "aaaa", "difficulty": "easy"},
        {"word": "apple", "difficulty": "extreme"},
        "apple",
    ],
)
def test_invalid_word_entries(bad) -> None:
    with pytest.raises(ContentError, match="entry 45"):
        parse_words(good_words() + [bad])


def test_duplicate_word_and_small_pool() -> None:
    with pytest.raises(ContentError, match="duplicate"):
        parse_words(good_words() + [good_words()[0]])
    with pytest.raises(ContentError, match="at least 15 hard"):
        parse_words([w for w in good_words() if w["difficulty"] != "hard"])


def puzzle(answer="Frozen", **over):
    return {"emojis": "🧊", "answer": answer, "alternatives": [], "category": "Movie", **over}


@pytest.mark.parametrize(
    "bad",
    [
        puzzle(emojis=""),
        puzzle(answer="!!"),
        puzzle(alternatives="Frozen 2"),
        puzzle(alternatives=[""]),
        puzzle(category=""),
        puzzle(answer="The Thing 0"),
    ],
)
def test_invalid_emoji_entries(bad) -> None:
    good = [puzzle(f"Thing {i}") for i in range(15)]
    with pytest.raises(ContentError, match="entry 15"):
        parse_emoji(good + [bad])


def test_invalid_topics() -> None:
    good = [f"Topic {i}" for i in range(5)]
    assert parse_topics(good) == good
    for bad in ["", "x" * 41, 7, "topic 0"]:
        with pytest.raises(ContentError):
            parse_topics(good + [bad])
