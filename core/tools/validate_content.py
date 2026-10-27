"""Check the Guess Race and Name It content in core/content/ and print counts.

Usage: python tools/validate_content.py

Runs every check the server runs at startup (characters, lengths, length bands, duplicates,
blocklist, missing fields, emoji versions: Emoji 13.1 or older, no skin tones, no ZWJ), plus
a few reports the server does not need: repeated emoji strings, answers that appear as another
puzzle's alternative, and counts by type, difficulty and category. Exits 1 on any problem.
"""

import sys
import time
import tracemalloc
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from games.content_rules import (  # noqa: E402
    ContentError,
    anagram_index,
    load_all,
    load_emoji_table,
    split_emoji,
)
from games.normalize import normalize  # noqa: E402


def table(title: str, counts: Counter) -> None:
    print(f"\n{title}")
    for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {name:<16} {n:>6}")


def main() -> int:
    tracemalloc.start()
    started = time.perf_counter()
    try:
        words, emoji, topics = load_all()
    except ContentError as exc:
        print(exc, file=sys.stderr)
        return 1
    seconds = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    problems: list[str] = []
    emoji_table = load_emoji_table()
    seen_strings: dict[str, str] = {}
    for p in emoji:
        if p.emojis in seen_strings:
            problems.append(
                f"emojis {p.emojis} used for {seen_strings[p.emojis]!r} and {p.answer!r}"
            )
        seen_strings[p.emojis] = p.answer
    answers = {normalize(p.answer): p.answer for p in emoji}
    overlaps = sorted(
        f"{p.answer!r} lists {alt!r}, the answer of another puzzle"
        for p in emoji
        for alt in p.alternatives
        if normalize(alt) in answers and answers[normalize(alt)] != p.answer
    )
    versions = Counter(
        f"Emoji {emoji_table[e]:g}"
        for p in emoji
        for e in (split_emoji(p.emojis, emoji_table) or [])
    )

    print(f"Loaded and validated in {seconds:.2f} s, peak {peak / 1_000_000:.1f} MB")
    print(f"Words: {len(words)}   Emoji puzzles: {len(emoji)}   Topics: {len(topics)}")
    table("Words by difficulty", Counter(w.difficulty for w in words))
    table("Words by length", Counter(f"{len(w.word)} letters" for w in words))
    groups = [g for g in anagram_index(w.word for w in words).values() if len(g) > 1]
    print(f"\nAnagram groups (several accepted answers): {len(groups)}")
    table("Emoji by difficulty", Counter(p.difficulty for p in emoji))
    table("Emoji by category", Counter(p.category for p in emoji))
    table("Emoji versions used", versions)
    if overlaps:
        print(f"\nNote: {len(overlaps)} alternatives are also another puzzle's answer:")
        for line in overlaps:
            print(f"  - {line}")
    if problems:
        print("\nProblems:", *(f"  - {p}" for p in problems), sep="\n", file=sys.stderr)
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
