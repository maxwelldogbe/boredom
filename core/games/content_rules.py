"""Rules for the JSON content in core/content/: parsing, validation, blocklist, anagrams.

Nothing is loaded at import, so the build and check tools can use these rules on files that
are not valid yet. games.content loads the shipped files. Sources: core/content/SOURCES.md.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path
from typing import Any

from games.normalize import normalize

CONTENT_DIR = Path(__file__).resolve().parents[1] / "content"
DIFFICULTIES = ("easy", "medium", "hard")
WORD_MIN, WORD_MAX = 4, 9
WORD_BANDS = {"easy": (4, 5), "medium": (6, 7), "hard": (8, 9)}  # documented in PROTOCOL.md
MIN_PER_POOL = 15  # the most rounds a Guess Race game can have
TOPIC_MAX = 40
MAX_EMOJI_VERSION = 13.1
MAX_SEQUENCE = 3  # longest allowed emoji sequence, in code points (keycaps)


class ContentError(RuntimeError):
    """A content file is missing or invalid."""


@dataclass(frozen=True)
class Word:
    word: str
    difficulty: str


@dataclass(frozen=True)
class EmojiPuzzle:
    emojis: str
    answer: str
    alternatives: tuple[str, ...]
    category: str
    difficulty: str = "medium"


@dataclass(frozen=True)
class Blocklist:
    """Exact words, plus roots that block every word containing them."""

    words: frozenset[str]
    roots: tuple[str, ...]


def _read(name: str) -> list[Any]:
    path = CONTENT_DIR / name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContentError(f"{path}: cannot read JSON ({exc})") from exc
    if not isinstance(data, list):
        raise ContentError(f"{path}: top level must be a JSON array")
    return data


def _raise_all(name: str, problems: list[str]) -> None:
    if problems:
        lines = "\n".join(f"  - {p}" for p in problems)
        raise ContentError(f"content/{name}: {len(problems)} problem(s):\n{lines}")


# ----- blocklist --------------------------------------------------------------------------------


def parse_blocklist(text: str) -> Blocklist:
    words, roots = set(), []
    for line in text.splitlines():
        entry = line.strip().lower()
        if not entry or entry.startswith("#"):
            continue
        if entry.startswith("*"):
            roots.append(entry[1:])
        else:
            words.add(entry)
    return Blocklist(frozenset(words), tuple(roots))


def load_blocklist(name: str = "blocklist.txt") -> Blocklist:
    path = CONTENT_DIR / name
    try:
        return parse_blocklist(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ContentError(f"{path}: cannot read ({exc})") from exc


def is_blocked(word: str, blocklist: Blocklist) -> bool:
    """True if the lowercase word is listed or contains a blocked root."""
    word = word.lower()
    return word in blocklist.words or any(root in word for root in blocklist.roots)


def text_blocked(text: str, blocklist: Blocklist) -> bool:
    """True if any word of a free-text answer is blocked."""
    return any(is_blocked(token, blocklist) for token in text.lower().replace("-", " ").split())


# ----- words and anagrams ------------------------------------------------------------------------


def band_for_length(length: int) -> str:
    return next(d for d, (lo, hi) in WORD_BANDS.items() if lo <= length <= hi)


def letters_key(word: str) -> str:
    """Anagram key: the word's letters in order. Anagrams share a key (and count as one puzzle)."""
    return "".join(sorted(word.lower()))


def anagram_index(words: Iterable[str]) -> dict[str, tuple[str, ...]]:
    groups: dict[str, list[str]] = {}
    for word in words:
        groups.setdefault(letters_key(word), []).append(word)
    return {key: tuple(group) for key, group in groups.items()}


def has_scramble(word: str, pool: set[str] | frozenset[str], blocklist: Blocklist) -> bool:
    """True if some arrangement of `word` may be shown: not the word, listed or blocked.

    Stops at the first acceptable arrangement, which is almost always the second one tried.
    """
    return any(
        s != word and s not in pool and not is_blocked(s, blocklist)
        for s in ("".join(p) for p in permutations(word))
    )


def parse_words(
    data: list[Any], name: str = "words.json", blocklist: Blocklist | None = None
) -> list[Word]:
    """Validate word entries: {word: a-z, 4..9 letters, difficulty matching its length band}.

    No duplicates, no blocklisted words, and every word must have at least one scramble that is
    not itself a listed or blocked word.
    """
    blocklist = blocklist or Blocklist(frozenset(), ())
    words: list[Word] = []
    problems: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            problems.append(f"entry {i}: must be an object")
            continue
        word, difficulty = item.get("word"), item.get("difficulty")
        if not (isinstance(word, str) and word.isascii() and word.isalpha() and word.islower()):
            problems.append(f"entry {i}: word must be lowercase letters a-z")
            continue
        if not WORD_MIN <= len(word) <= WORD_MAX:
            problems.append(f"entry {i}: word must be {WORD_MIN} to {WORD_MAX} letters")
            continue
        if len(set(word)) < 2:
            problems.append(f"entry {i}: word needs at least two different letters to scramble")
            continue
        if difficulty not in DIFFICULTIES:
            problems.append(f"entry {i}: difficulty must be one of {DIFFICULTIES}")
            continue
        lo, hi = WORD_BANDS[difficulty]
        if not lo <= len(word) <= hi:
            problems.append(f"entry {i}: {difficulty} words have {lo} to {hi} letters ({word!r})")
        if word in seen:
            problems.append(f"entry {i}: duplicate word {word!r}")
        if is_blocked(word, blocklist):
            problems.append(f"entry {i}: blocklisted word {word!r}")
        seen.add(word)
        words.append(Word(word, difficulty))
    for w in words:
        if not has_scramble(w.word, seen, blocklist):
            problems.append(f"word {w.word!r}: every arrangement is a listed or blocked word")
    for difficulty in DIFFICULTIES:
        if sum(w.difficulty == difficulty for w in words) < MIN_PER_POOL:
            problems.append(f"need at least {MIN_PER_POOL} {difficulty} words")
    _raise_all(name, problems)
    return words


# ----- emoji ------------------------------------------------------------------------------------


def parse_emoji_table(text: str) -> dict[str, float]:
    """The allowed emoji table: one `<emoji>\\t<version>\\t<name>` line per sequence."""
    table: dict[str, float] = {}
    for line in text.splitlines():
        if line and not line.startswith("#"):
            emoji, version, _ = line.split("\t", 2)
            table[emoji] = float(version)
    return table


def load_emoji_table(name: str = "unicode_emoji.txt") -> dict[str, float]:
    path = CONTENT_DIR / name
    try:
        return parse_emoji_table(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContentError(f"{path}: cannot read ({exc})") from exc


def split_emoji(text: str, table: dict[str, float]) -> list[str] | None:
    """Split a puzzle string into allowed emoji (longest match first), or None if impossible."""
    out, i = [], 0
    while i < len(text):
        for size in range(min(MAX_SEQUENCE, len(text) - i), 0, -1):
            piece = text[i : i + size]
            if piece in table and table[piece] <= MAX_EMOJI_VERSION:
                out.append(piece)
                i += size
                break
        else:
            return None
    return out


def parse_emoji(
    data: list[Any],
    name: str = "emoji.json",
    table: dict[str, float] | None = None,
    blocklist: Blocklist | None = None,
) -> list[EmojiPuzzle]:
    """Validate puzzles: {emojis, answer, alternatives[], category, difficulty}. Answers unique.

    With a `table`, every emoji must be an allowed one (Emoji 13.1 or older, no skin tones,
    no ZWJ sequences).
    """
    blocklist = blocklist or Blocklist(frozenset(), ())
    puzzles: list[EmojiPuzzle] = []
    problems: list[str] = []
    seen: dict[str, int] = {}
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            problems.append(f"entry {i}: must be an object")
            continue
        emojis, answer = item.get("emojis"), item.get("answer")
        alternatives, category = item.get("alternatives"), item.get("category")
        difficulty = item.get("difficulty", "medium")
        bad = []
        if not isinstance(emojis, str) or not emojis.strip():
            bad.append("emojis must be a non-empty string")
        elif table is not None and split_emoji(emojis, table) is None:
            bad.append(f"emojis {emojis!r} include a non-emoji or an unsupported emoji")
        if not isinstance(answer, str) or not normalize(answer):
            bad.append("answer must contain letters or digits")
        elif text_blocked(answer, blocklist):
            bad.append(f"blocklisted answer {answer!r}")
        if not isinstance(alternatives, list) or not all(
            isinstance(a, str) and normalize(a) for a in alternatives
        ):
            bad.append("alternatives must be a list of non-empty strings")
        if not isinstance(category, str) or not category.strip():
            bad.append("category must be a non-empty string")
        if difficulty not in DIFFICULTIES:
            bad.append(f"difficulty must be one of {DIFFICULTIES}")
        if bad:
            problems.extend(f"entry {i}: {p}" for p in bad)
            continue
        key = normalize(answer)
        if key in seen:
            problems.append(f"entry {i}: duplicate answer {answer!r} (entry {seen[key]})")
        seen[key] = i
        puzzles.append(EmojiPuzzle(emojis, answer, tuple(alternatives), category, difficulty))
    if len(puzzles) < MIN_PER_POOL:
        problems.append(f"need at least {MIN_PER_POOL} puzzles")
    _raise_all(name, problems)
    return puzzles


def parse_topics(data: list[Any], name: str = "topics.json") -> list[str]:
    """Validate topics: unique non-empty strings of at most TOPIC_MAX characters."""
    topics, seen = [], set()
    for i, item in enumerate(data):
        if not isinstance(item, str) or not item.strip() or len(item) > TOPIC_MAX:
            raise ContentError(
                f"content/{name} entry {i}: topic must be 1 to {TOPIC_MAX} characters"
            )
        if item.strip().lower() in seen:
            raise ContentError(f"content/{name} entry {i}: duplicate topic {item!r}")
        seen.add(item.strip().lower())
        topics.append(item.strip())
    if len(topics) < 5:
        raise ContentError(f"content/{name}: need at least 5 topics")
    return topics


def load_all() -> tuple[tuple[Word, ...], tuple[EmojiPuzzle, ...], tuple[str, ...]]:
    """Read and validate every content file; one ContentError lists all problems found."""
    blocklist = load_blocklist()
    table = load_emoji_table()
    errors: list[str] = []
    loaded: list[Any] = []
    for loader in (
        lambda: parse_words(_read("words.json"), blocklist=blocklist),
        lambda: parse_emoji(_read("emoji.json"), table=table, blocklist=blocklist),
        lambda: parse_topics(_read("topics.json")),
    ):
        try:
            loaded.append(tuple(loader()))
        except ContentError as exc:
            errors.append(str(exc))
    if errors:
        raise ContentError("Invalid game content:\n" + "\n".join(errors))
    return loaded[0], loaded[1], loaded[2]
