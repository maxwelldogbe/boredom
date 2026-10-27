"""The game content in core/content/ (words, emoji puzzles, topics), loaded once at import.

A broken file stops the server at startup with one error that lists every problem found.
The rules live in games.content_rules; sources and licences in core/content/SOURCES.md.
"""

from games.content_rules import (
    CONTENT_DIR,
    DIFFICULTIES,
    TOPIC_MAX,
    Blocklist,
    ContentError,
    EmojiPuzzle,
    Word,
    load_all,
    load_blocklist,
    parse_emoji,
    parse_topics,
    parse_words,
)

__all__ = [
    "BLOCKLIST",
    "CONTENT_DIR",
    "DIFFICULTIES",
    "EMOJI",
    "TOPICS",
    "TOPIC_MAX",
    "WORDS",
    "ContentError",
    "EmojiPuzzle",
    "Word",
    "parse_emoji",
    "parse_topics",
    "parse_words",
]

BLOCKLIST: Blocklist = load_blocklist()
WORDS, EMOJI, TOPICS = load_all()
