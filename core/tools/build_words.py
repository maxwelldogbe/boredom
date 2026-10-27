"""Build core/content/words.json from SCOWL (see core/content/SOURCES.md).

Usage: python tools/build_words.py <path to an extracted scowl-2020.12.07 directory>

SCOWL sorts words into size levels by commonness (10 = most common ... 95 = rarest). Difficulty
follows the documented length bands (easy 4-5 letters, medium 6-7, hard 8-9); commonness decides
which words get in at all: each band accepts words up to a maximum level, longer bands a little
further. Inflected forms (plurals, -ed, -ing...) are kept only when they are very common
themselves. Proper nouns, abbreviations, blocklisted words and words without a scramble that
is not itself a word are left out.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from games.content_rules import (  # noqa: E402
    CONTENT_DIR,
    WORD_MAX,
    WORD_MIN,
    band_for_length,
    has_scramble,
    is_blocked,
    load_blocklist,
)

MAX_LEVEL = {"easy": 35, "medium": 35, "hard": 40}
INFLECTION_MAX_LEVEL = 20  # inflected forms must be at least this common
PROPER_MAX_LEVEL = 20  # a word that is also a name must be at least this common


def read_lists(final: Path, pattern: str) -> dict[str, int]:
    """Word -> lowest (most common) level among SCOWL files matching `pattern`."""
    levels: dict[str, int] = {}
    for path in final.glob(pattern):
        level = int(path.suffix[1:])
        for line in path.read_text(encoding="latin-1").splitlines():
            word = line.strip()
            if word:
                levels[word] = min(level, levels.get(word, 99))
    return levels


def bases(word: str) -> set[str]:
    """Possible base forms if `word` is a regular inflection (plural, -ed, -ing, -er, -est)."""
    out: set[str] = set()
    for suffix in ("s", "es", "ed", "d", "ing", "er", "ers", "est", "ly"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            stem = word[: -len(suffix)]
            out |= {stem, stem + "e"}
            if len(stem) >= 2 and stem[-1] == stem[-2]:
                out.add(stem[:-1])  # stopped -> stop
            if stem.endswith("i"):
                out.add(stem[:-1] + "y")  # cities -> city, carried -> carry
    return out


def build(scowl: Path) -> list[dict[str, str]]:
    final = next(scowl.glob("final"), None) or next(scowl.glob("*/final"))
    words = read_lists(final, "english-words.*")
    for word, level in read_lists(final, "american-words.*").items():
        words[word] = min(level, words.get(word, 99))
    names = {
        w.lower()
        for pattern in ("*proper-names.*", "english-upper.*", "american-upper.*")
        for w in read_lists(final, pattern)
    }
    abbreviations = {
        w.lower() for p in ("*abbreviations.*", "*contractions.*") for w in read_lists(final, p)
    }
    blocklist = load_blocklist()

    candidates: dict[str, int] = {}
    for word, level in words.items():
        if not (word.isascii() and word.isalpha() and word.islower()):
            continue
        if not WORD_MIN <= len(word) <= WORD_MAX or len(set(word)) < 2:
            continue
        if level > MAX_LEVEL[band_for_length(len(word))]:
            continue
        if word in abbreviations or (word in names and level > PROPER_MAX_LEVEL):
            continue
        if is_blocked(word, blocklist):
            continue
        candidates[word] = level
    every_word = set(words)
    kept = {
        w: lvl
        for w, lvl in candidates.items()
        if lvl <= INFLECTION_MAX_LEVEL or not (bases(w) & every_word)
    }
    pool = set(kept)
    kept = {w: lvl for w, lvl in kept.items() if has_scramble(w, pool, blocklist)}
    return [
        {"word": w, "difficulty": band_for_length(len(w))}
        for w in sorted(kept, key=lambda w: (len(w), kept[w], w))
    ]


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    entries = build(Path(sys.argv[1]))
    out = CONTENT_DIR / "words.json"
    text = "[\n" + ",\n".join(json.dumps(e) for e in entries) + "\n]\n"
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {len(entries)} words to {out}")


if __name__ == "__main__":
    main()
