"""Loads and validates the JSON content in core/content/ (words, emoji puzzles, topics).

Loaded once at import, so a broken file stops the server at startup with a clear message.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from games.normalize import normalize

CONTENT_DIR = Path(__file__).resolve().parents[1] / "content"
DIFFICULTIES = ("easy", "medium", "hard")
WORD_MIN, WORD_MAX = 4, 9
MIN_PER_POOL = 15  # the most rounds a Guess Race game can have
TOPIC_MAX = 40


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


def _read(name: str) -> list[Any]:
    path = CONTENT_DIR / name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContentError(f"{path}: cannot read JSON ({exc})") from exc
    if not isinstance(data, list):
        raise ContentError(f"{path}: top level must be a JSON array")
    return data


def _fail(name: str, index: int, problem: str) -> ContentError:
    return ContentError(f"content/{name} entry {index}: {problem}")


def parse_words(data: list[Any], name: str = "words.json") -> list[Word]:
    """Validate word entries: {word: a-z, 4..9 letters, difficulty}. No duplicates."""
    words, seen = [], set()
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise _fail(name, i, "must be an object")
        word, difficulty = item.get("word"), item.get("difficulty")
        if not (isinstance(word, str) and word.isascii() and word.isalpha() and word.islower()):
            raise _fail(name, i, "word must be lowercase letters a-z")
        if not WORD_MIN <= len(word) <= WORD_MAX:
            raise _fail(name, i, f"word must be {WORD_MIN} to {WORD_MAX} letters")
        if len(set(word)) < 2:
            raise _fail(name, i, "word needs at least two different letters to scramble")
        if difficulty not in DIFFICULTIES:
            raise _fail(name, i, f"difficulty must be one of {DIFFICULTIES}")
        if word in seen:
            raise _fail(name, i, f"duplicate word {word!r}")
        seen.add(word)
        words.append(Word(word, difficulty))
    for difficulty in DIFFICULTIES:
        if sum(w.difficulty == difficulty for w in words) < MIN_PER_POOL:
            raise ContentError(f"content/{name}: need at least {MIN_PER_POOL} {difficulty} words")
    return words


def parse_emoji(data: list[Any], name: str = "emoji.json") -> list[EmojiPuzzle]:
    """Validate puzzles: {emojis, answer, alternatives[], category}. Answers unique."""
    puzzles, seen = [], set()
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise _fail(name, i, "must be an object")
        emojis, answer = item.get("emojis"), item.get("answer")
        alternatives, category = item.get("alternatives"), item.get("category")
        if not isinstance(emojis, str) or not emojis.strip():
            raise _fail(name, i, "emojis must be a non-empty string")
        if not isinstance(answer, str) or not normalize(answer):
            raise _fail(name, i, "answer must contain letters or digits")
        if not isinstance(alternatives, list) or not all(
            isinstance(a, str) and normalize(a) for a in alternatives
        ):
            raise _fail(name, i, "alternatives must be a list of non-empty strings")
        if not isinstance(category, str) or not category.strip():
            raise _fail(name, i, "category must be a non-empty string")
        if normalize(answer) in seen:
            raise _fail(name, i, f"duplicate answer {answer!r}")
        seen.add(normalize(answer))
        puzzles.append(EmojiPuzzle(emojis, answer, tuple(alternatives), category))
    if len(puzzles) < MIN_PER_POOL:
        raise ContentError(f"content/{name}: need at least {MIN_PER_POOL} puzzles")
    return puzzles


def parse_topics(data: list[Any], name: str = "topics.json") -> list[str]:
    """Validate topics: unique non-empty strings of at most TOPIC_MAX characters."""
    topics, seen = [], set()
    for i, item in enumerate(data):
        if not isinstance(item, str) or not item.strip() or len(item) > TOPIC_MAX:
            raise _fail(name, i, f"topic must be 1 to {TOPIC_MAX} characters")
        if item.strip().lower() in seen:
            raise _fail(name, i, f"duplicate topic {item!r}")
        seen.add(item.strip().lower())
        topics.append(item.strip())
    if len(topics) < 5:
        raise ContentError(f"content/{name}: need at least 5 topics")
    return topics


WORDS: tuple[Word, ...] = tuple(parse_words(_read("words.json")))
EMOJI: tuple[EmojiPuzzle, ...] = tuple(parse_emoji(_read("emoji.json")))
TOPICS: tuple[str, ...] = tuple(parse_topics(_read("topics.json")))
