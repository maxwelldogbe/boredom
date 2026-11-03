"""Check core/content/name_it_lists.json and print the answer count per topic.

Run from core/: python tools/validate_name_it_lists.py  (exit code 1 when invalid)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from games.name_it_lists import check_lists, read_lists  # noqa: E402


def main() -> int:
    data = read_lists()
    problems = check_lists(data)
    for topic in data if isinstance(data, list) else []:
        if isinstance(topic, dict):
            print(f"{topic.get('id')}: {len(topic.get('answers') or [])} answers")
    for problem in problems:
        print(f"PROBLEM: {problem}")
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
