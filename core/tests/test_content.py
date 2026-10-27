"""Content files: shipped files are valid, and the validators reject broken entries."""

import json
from collections import Counter

import pytest

from games import content_rules
from games.content import BLOCKLIST, EMOJI, TOPICS, WORDS
from games.content_rules import (
    WORD_BANDS,
    Blocklist,
    ContentError,
    has_scramble,
    is_blocked,
    load_all,
    load_emoji_table,
    parse_blocklist,
    parse_emoji,
    parse_topics,
    parse_words,
    split_emoji,
)
from games.normalize import normalize

TABLE = load_emoji_table()


def test_shipped_content_sizes() -> None:
    assert len(WORDS) >= 10_000 and len(EMOJI) >= 2_000 and len(TOPICS) == 50
    by_band = Counter(w.difficulty for w in WORDS)
    assert all(by_band[d] >= 3_000 for d in WORD_BANDS), by_band


def test_words_have_lengths_characters_and_bands() -> None:
    for w in WORDS:
        lo, hi = WORD_BANDS[w.difficulty]
        assert lo <= len(w.word) <= hi and w.word.isascii() and w.word.isalpha(), w
        assert w.word.islower(), w


def test_no_duplicates() -> None:
    assert len({w.word for w in WORDS}) == len(WORDS)
    assert len({normalize(p.answer) for p in EMOJI}) == len(EMOJI)
    assert len({p.emojis for p in EMOJI}) == len(EMOJI)


def test_shipped_content_has_no_blocklisted_words() -> None:
    assert not [w.word for w in WORDS if is_blocked(w.word, BLOCKLIST)]
    tokens = {t for p in EMOJI for t in p.answer.lower().replace("-", " ").split()}
    assert not [t for t in tokens if is_blocked(t, BLOCKLIST)]


def test_every_emoji_is_supported() -> None:
    for p in EMOJI:
        pieces = split_emoji(p.emojis, TABLE)
        assert pieces, p
        assert all(TABLE[e] <= 13.1 for e in pieces), p
        assert "‍" not in p.emojis and not any(0x1F3FB <= ord(c) <= 0x1F3FF for c in p.emojis)
    assert {p.difficulty for p in EMOJI} == {"easy", "medium", "hard"}


def test_emoji_table_rejects_newer_skin_toned_and_zwj_emoji() -> None:
    for bad in ["🫠", "👍🏽", "👨‍🍳", "🏴‍☠️", "🪽", "abc", "🐶x"]:
        assert split_emoji(bad, TABLE) is None, bad
    assert split_emoji("🐶🇫🇷1️⃣", TABLE) == ["🐶", "🇫🇷", "1️⃣"]


# ----- blocklist -------------------------------------------------------------------------------


def test_blocklist_matches_exact_words_and_roots() -> None:
    blocklist = parse_blocklist("# comment\nspic\n*fuck\n\n")
    assert is_blocked("spic", blocklist) and is_blocked("SPIC", blocklist)
    assert not is_blocked("spiced", blocklist) and not is_blocked("spices", blocklist)
    assert is_blocked("motherfucker", blocklist)
    assert not is_blocked("fork", blocklist)


def test_blocklisted_word_is_rejected() -> None:
    blocklist = Blocklist(frozenset({"apple"}), ())
    with pytest.raises(ContentError, match="blocklisted word 'apple'"):
        parse_words([*good_words(), {"word": "apple", "difficulty": "easy"}], blocklist=blocklist)


def test_blocklisted_emoji_answer_is_rejected() -> None:
    good = [puzzle(f"Thing {i}") for i in range(15)]
    blocklist = Blocklist(frozenset({"kill"}), ())
    with pytest.raises(ContentError, match="blocklisted answer"):
        parse_emoji([*good, puzzle("Kill Bill")], blocklist=blocklist)


# ----- word validation -------------------------------------------------------------------------


def good_words(n=15):
    """n valid words per band, each of the band's shortest length."""
    out = []
    for d, (lo, _) in WORD_BANDS.items():
        for i in range(n):
            out.append({"word": ("bc" + chr(97 + i) + "xyzwvu")[:lo], "difficulty": d})
    return out


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
        {"word": "apple", "difficulty": "hard"},  # 5 letters is the easy band
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


def test_word_needs_a_scramble_that_is_not_a_word() -> None:
    assert has_scramble("listen", {"listen", "silent"}, BLOCKLIST)
    assert not has_scramble("abab", {"abab", "aabb", "abba", "baab", "baba", "bbaa"}, BLOCKLIST)
    every = [
        {"word": w, "difficulty": "easy"} for w in ("abab", "aabb", "abba", "baab", "baba", "bbaa")
    ]
    with pytest.raises(ContentError, match="every arrangement"):
        parse_words(good_words() + every)


def test_every_problem_is_listed_at_once() -> None:
    bad = [{"word": "Apple", "difficulty": "easy"}, {"word": "abc", "difficulty": "easy"}]
    with pytest.raises(ContentError) as exc:
        parse_words(good_words() + bad)
    assert "2 problem(s)" in str(exc.value)
    assert "entry 45" in str(exc.value) and "entry 46" in str(exc.value)


# ----- emoji validation ------------------------------------------------------------------------


def puzzle(answer="Frozen", **over):
    return {
        "emojis": "🧊",
        "answer": answer,
        "alternatives": [],
        "category": "Movie",
        "difficulty": "easy",
        **over,
    }


@pytest.mark.parametrize(
    "bad",
    [
        puzzle(emojis=""),
        puzzle(answer="!!"),
        puzzle(alternatives="Frozen 2"),
        puzzle(alternatives=[""]),
        puzzle(category=""),
        puzzle(difficulty="extreme"),
        puzzle(answer="The Thing 0"),
        puzzle(emojis="👨‍🍳"),
        puzzle(emojis="🫠"),
        puzzle(emojis="👍🏽"),
        puzzle(emojis="ice"),
    ],
)
def test_invalid_emoji_entries(bad) -> None:
    good = [puzzle(f"Thing {i}") for i in range(15)]
    with pytest.raises(ContentError, match="entry 15"):
        parse_emoji(good + [bad], table=TABLE)


def test_invalid_topics() -> None:
    good = [f"Topic {i}" for i in range(5)]
    assert parse_topics(good) == good
    for bad in ["", "x" * 41, 7, "topic 0"]:
        with pytest.raises(ContentError):
            parse_topics(good + [bad])


# ----- startup ---------------------------------------------------------------------------------


def test_startup_fails_on_a_bad_file_and_lists_every_problem(tmp_path, monkeypatch) -> None:
    real = content_rules.CONTENT_DIR
    for name in ("blocklist.txt", "unicode_emoji.txt", "topics.json"):
        (tmp_path / name).write_text((real / name).read_text(encoding="utf-8"), encoding="utf-8")
    words = [
        *good_words(),
        {"word": "Apple", "difficulty": "easy"},
        {"word": "ab", "difficulty": "x"},
    ]
    emoji = [puzzle(f"Thing {i}") for i in range(15)] + [puzzle("Chef", emojis="👨‍🍳")]
    (tmp_path / "words.json").write_text(json.dumps(words), encoding="utf-8")
    (tmp_path / "emoji.json").write_text(json.dumps(emoji), encoding="utf-8")
    monkeypatch.setattr(content_rules, "CONTENT_DIR", tmp_path)
    with pytest.raises(ContentError) as exc:
        load_all()
    message = str(exc.value)
    assert message.startswith("Invalid game content:")
    assert "content/words.json: 2 problem(s)" in message
    assert "content/emoji.json: 1 problem(s)" in message and "unsupported emoji" in message


def test_startup_fails_on_unreadable_json(tmp_path, monkeypatch) -> None:
    real = content_rules.CONTENT_DIR
    for name in ("blocklist.txt", "unicode_emoji.txt", "topics.json", "emoji.json"):
        (tmp_path / name).write_text((real / name).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "words.json").write_text("[{", encoding="utf-8")
    monkeypatch.setattr(content_rules, "CONTENT_DIR", tmp_path)
    with pytest.raises(ContentError, match="words.json: cannot read JSON"):
        load_all()
