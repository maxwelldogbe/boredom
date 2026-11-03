"""The Name It Streak answer lists (core/content/name_it_lists.json): loading and checks.

Each topic is {id, name, emoji, answers: [{name, aliases: [...]}]}. Answers match on their
folded form: the shared normalize() after accent folding (NFKD, combining marks dropped).
A broken file stops the server at startup (ContentError lists every problem); the same
checks run from core/tools/validate_name_it_lists.py.
"""

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from games.constants import SOLO_NAMEIT_MIN_ANSWERS, SOLO_NAMEIT_TOPICS
from games.content_rules import CONTENT_DIR, ContentError
from games.normalize import normalize

LISTS_FILE = "name_it_lists.json"
TEXT_MAX = 40


def fold(text: str) -> str:
    """Accent-folded normalize(): "Côte d'Ivoire" and "cote divoire" both -> "cotedivoire"."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return normalize(stripped)


@dataclass(frozen=True)
class Topic:
    id: str
    name: str
    emoji: str
    names: tuple[str, ...]  # display name per entry
    index: dict[str, int]  # folded name or alias -> entry


def check_lists(data: Any) -> list[str]:
    """Every problem in the parsed file (empty when valid)."""
    if not isinstance(data, list):
        return ["the file must hold a list of topics"]
    problems: list[str] = []
    seen_ids: set[str] = set()
    for t, topic in enumerate(data):
        where = f"topic {t + 1}"
        if not isinstance(topic, dict):
            problems.append(f"{where}: not an object")
            continue
        for key in ("id", "name", "emoji", "answers"):
            if key not in topic:
                problems.append(f"{where}: missing {key}")
        tid = topic.get("id")
        if isinstance(tid, str):
            where = f"topic {tid}"
            if tid in seen_ids:
                problems.append(f"{where}: duplicate topic id")
            seen_ids.add(tid)
        for key in ("id", "name", "emoji"):
            value = topic.get(key)
            if key in topic and (not isinstance(value, str) or not value.strip()):
                problems.append(f"{where}: {key} must be a non-empty string")
        answers = topic.get("answers")
        if not isinstance(answers, list):
            if "answers" in topic:
                problems.append(f"{where}: answers must be a list")
            continue
        if len(answers) < SOLO_NAMEIT_MIN_ANSWERS:
            problems.append(f"{where}: {len(answers)} answers, needs {SOLO_NAMEIT_MIN_ANSWERS}")
        owner: dict[str, int] = {}
        for a, entry in enumerate(answers):
            label = f"{where} answer {a + 1}"
            if not isinstance(entry, dict) or "name" not in entry or "aliases" not in entry:
                problems.append(f"{label}: needs name and aliases")
                continue
            aliases = entry["aliases"]
            if not isinstance(aliases, list):
                problems.append(f"{label}: aliases must be a list")
                continue
            for i, text in enumerate([entry["name"], *aliases]):
                kind = "name" if i == 0 else "alias"
                if not isinstance(text, str) or not text.strip():
                    problems.append(f"{label}: empty {kind}")
                    continue
                if len(text) > TEXT_MAX:
                    problems.append(f"{label}: {kind} {text!r} is over {TEXT_MAX} characters")
                key = fold(text)
                if not key:
                    problems.append(f"{label}: {kind} {text!r} has no letters or digits")
                    continue
                if key in owner and owner[key] != a:
                    other = answers[owner[key]].get("name", "?")
                    what = "duplicate answer" if kind == "name" else "alias collides with"
                    problems.append(f"{label}: {what} {other!r} ({text!r})")
                owner.setdefault(key, a)
    expected = [t["id"] for t in SOLO_NAMEIT_TOPICS]
    found = [t.get("id") for t in data if isinstance(t, dict)]
    if found != expected:
        problems.append(f"topic ids {found} must match SOLO_NAMEIT_TOPICS {expected}")
    return problems


def build_topics(data: list[dict[str, Any]]) -> dict[str, Topic]:
    topics = {}
    for topic in data:
        names = tuple(entry["name"] for entry in topic["answers"])
        index: dict[str, int] = {}
        for i, entry in enumerate(topic["answers"]):
            for text in (entry["name"], *entry["aliases"]):
                index.setdefault(fold(text), i)
        topics[topic["id"]] = Topic(topic["id"], topic["name"], topic["emoji"], names, index)
    return topics


def read_lists(path: Path | None = None) -> Any:
    path = path or CONTENT_DIR / LISTS_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContentError(f"{path}: cannot read JSON ({exc})") from exc


def load_lists(path: Path | None = None) -> dict[str, Topic]:
    """The topics, or ContentError listing every problem."""
    data = read_lists(path)
    problems = check_lists(data)
    if problems:
        lines = "\n".join(f"  - {p}" for p in problems)
        raise ContentError(f"content/{LISTS_FILE}: {len(problems)} problem(s):\n{lines}")
    return build_topics(data)


NAME_IT_TOPICS: dict[str, Topic] = load_lists()
