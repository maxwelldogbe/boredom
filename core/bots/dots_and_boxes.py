"""Dots and Boxes bot. Reads the public board only (size and drawn lines).

easy: takes an available box half the time, else draws a random line.
medium: always takes a box; else a safe line (no third side on any box); else the line that
gives away the fewest boxes.
hard: medium plus chain play. Once no safe line is left the board is chains and loops: it
keeps control by double-dealing (leaving the last 2 boxes of a chain, or 4 of a loop) when
that wins more, and opens the component that loses least (hard-hearted handout for 2-chains).
With few safe lines left it searches every order of them, scoring the endgame exactly. The
search stops at the time budget and falls back to the medium choice.
"""

import random
import time
from functools import cache
from typing import Any

from games.dots_and_boxes import adjacent_boxes, all_lines, box_sides

Box = tuple[int, int]
SEARCH_SAFE_MAX = 8  # hard: search every order of the safe lines once this few remain
GROUND = None


class _Timeout(Exception):
    pass


@cache
def _geometry(
    size: int,
) -> tuple[tuple[str, ...], dict[str, tuple[Box, ...]], dict[Box, tuple[str, ...]]]:
    lines = tuple(all_lines(size))
    adj = {line: tuple(adjacent_boxes(line, size)) for line in lines}
    sides = {(r, c): box_sides(r, c) for r in range(size) for c in range(size)}
    return lines, adj, sides


class _Board:
    def __init__(self, size: int, drawn: set[str]) -> None:
        self.size = size
        self.lines, self.adj, self.sides = _geometry(size)
        self.drawn = drawn

    def drawn_count(self, box: Box) -> int:
        return sum(side in self.drawn for side in self.sides[box])

    def free(self) -> list[str]:
        return [line for line in self.lines if line not in self.drawn]

    def completes(self, line: str) -> bool:
        return any(self.drawn_count(b) == 3 for b in self.adj[line])

    def capturable(self) -> list[str]:
        return [line for line in self.free() if self.completes(line)]

    def safe(self) -> list[str]:
        return [
            line for line in self.free() if all(self.drawn_count(b) < 2 for b in self.adj[line])
        ]

    def gift(self, line: str) -> int:
        """Boxes the opponent can then take in a row after `line` is drawn (greedy)."""
        added = [line]
        self.drawn.add(line)
        taken = 0
        while True:
            grab = next((x for x in self.free() if self.completes(x)), None)
            if grab is None:
                break
            taken += sum(1 for b in self.adj[grab] if self.drawn_count(b) == 3)
            self.drawn.add(grab)
            added.append(grab)
        for line_id in added:
            self.drawn.discard(line_id)
        return taken

    def components(self) -> list[dict[str, Any]] | None:
        """Unclaimed boxes as chains and loops; None if any box has 3+ free sides."""
        open_boxes = [b for b in self.sides if self.drawn_count(b) < 4]
        links: dict[Box, list[tuple[str, Box | None]]] = {}
        for box in open_boxes:
            free = [s for s in self.sides[box] if s not in self.drawn]
            if len(free) > 2:
                return None
            links[box] = [(s, next((o for o in self.adj[s] if o != box), GROUND)) for s in free]
        seen: set[Box] = set()
        comps = []
        for start in open_boxes:
            if start in seen:
                continue
            boxes, ground, stack = [], 0, [start]
            seen.add(start)
            while stack:
                box = stack.pop()
                boxes.append(box)
                for _, other in links[box]:
                    if other is GROUND:
                        ground += 1
                    elif other not in seen:
                        seen.add(other)
                        stack.append(other)
            loop = ground == 0 and all(len(links[b]) == 2 for b in boxes)
            comps.append({"boxes": boxes, "loop": loop, "ground": ground, "links": links})
        return comps


@cache
def _opener_value(comps: tuple[tuple[int, bool], ...]) -> int:
    """Net boxes for the player who must open one of `comps` (both play perfectly)."""
    if not comps:
        return 0
    best = None
    for i, (length, loop) in enumerate(comps):
        if i and comps[i - 1] == comps[i]:
            continue
        rest = comps[:i] + comps[i + 1 :]
        r = _opener_value(rest)
        take = length + r
        if loop:
            keep = length - 8 - r  # take all but 4, hand out 4, the opener opens next
        elif length >= 3:
            keep = length - 4 - r  # take all but 2, hand out 2
        else:
            keep = None  # a short chain is opened so it cannot be double-dealt
        reply = take if keep is None else max(take, keep)
        if best is None or -reply > best:
            best = -reply
    assert best is not None
    return best


def _key(comps: list[dict[str, Any]]) -> tuple[tuple[int, bool], ...]:
    return tuple(sorted((len(c["boxes"]), c["loop"]) for c in comps))


def choose(view: dict[str, Any], rng: random.Random, difficulty: str, budget_ms: float) -> dict:
    """A legal {"type": "drawLine", "id"} for the player to move in `view`."""
    deadline = time.perf_counter() + budget_ms / 1000
    board = _Board(view["size"], set(view["lines"]))
    line = None
    if difficulty == "hard":
        try:
            line = _hard(board, rng, deadline)
        except _Timeout:
            line = None
    if line is None:
        board = _Board(view["size"], set(view["lines"]))  # untouched by an interrupted search
        line = _easy(board, rng) if difficulty == "easy" else _medium(board, rng)
    return {"type": "drawLine", "id": line}


def _easy(board: _Board, rng: random.Random) -> str:
    grabs = board.capturable()
    if grabs and rng.random() < 0.5:
        return rng.choice(grabs)
    return rng.choice(board.free())


def _medium(board: _Board, rng: random.Random) -> str:
    grabs = board.capturable()
    if grabs:
        return rng.choice(grabs)
    safe = board.safe()
    if safe:
        return rng.choice(safe)
    gifts = {line: board.gift(line) for line in board.free()}
    least = min(gifts.values())
    return rng.choice([line for line, n in gifts.items() if n == least])


def _check(deadline: float) -> None:
    if time.perf_counter() > deadline:
        raise _Timeout


def _hard(board: _Board, rng: random.Random, deadline: float) -> str | None:
    """The hard choice, or None to use the medium one."""
    grabs = board.capturable()
    if grabs:
        return _hard_capture(board, grabs, deadline)
    safe = board.safe()
    if safe:
        if len(safe) > SEARCH_SAFE_MAX:
            return None
        return _search_safe(board, safe, rng, deadline)
    return _open(board)


def _hard_capture(board: _Board, grabs: list[str], deadline: float) -> str:
    """Take a box, or double-deal when keeping control wins more."""
    if board.safe():
        return grabs[0]
    comps = board.components()
    if comps is None:
        return grabs[0]
    opened = [c for c in comps if any(len(c["links"][b]) == 1 for b in c["boxes"])]
    if len(opened) != 1:
        return grabs[0]
    current = opened[0]
    rest = [c for c in comps if c is not current]
    k = len(current["boxes"])
    loop_type = current["ground"] == 0
    if not rest or k != (4 if loop_type else 2):
        return grabs[0]
    _check(deadline)
    r = _opener_value(_key(rest))
    if -k - r <= k + r:
        return grabs[0]
    deal = _double_deal_line(current, loop_type)
    return deal if deal is not None else grabs[0]


def _path(comp: dict[str, Any]) -> list[Box]:
    """The boxes of an opened component in order, from an end with one free side."""
    links = comp["links"]
    start = next(b for b in comp["boxes"] if len(links[b]) == 1)
    order, prev = [start], None
    while True:
        here = order[-1]
        nxt = next((o for _, o in links[here] if o is not GROUND and o != prev), None)
        if nxt is None or nxt in order:
            return order
        prev = here
        order.append(nxt)


def _shared(comp: dict[str, Any], a: Box, b: Box) -> str | None:
    return next((s for s, o in comp["links"][a] if o == b), None)


def _double_deal_line(comp: dict[str, Any], loop_type: bool) -> str | None:
    path = _path(comp)
    if loop_type:  # A-B-C-D: cut B-C, leaving two dominoes
        return _shared(comp, path[1], path[2]) if len(path) == 4 else None
    if len(path) != 2:
        return None
    far = path[1]
    others = [s for s, o in comp["links"][far] if o != path[0]]
    return others[0] if len(comp["links"][far]) == 2 and others else None


def _open(board: _Board) -> str | None:
    """No safe line and nothing to take: open the component that loses least."""
    comps = board.components()
    if not comps:
        return None
    best, best_value = None, None
    for comp in sorted(comps, key=lambda c: (c["loop"], len(c["boxes"]))):
        rest = [c for c in comps if c is not comp]
        r = _opener_value(_key(rest))
        length = len(comp["boxes"])
        take = length + r
        if comp["loop"]:
            reply = max(take, length - 8 - r)
        elif length >= 3:
            reply = max(take, length - 4 - r)
        else:
            reply = take
        if best_value is None or -reply > best_value:
            best, best_value = comp, -reply
    assert best is not None
    return _opening_line(best)


def _opening_line(comp: dict[str, Any]) -> str:
    links = comp["links"]
    boxes = comp["boxes"]
    if not comp["loop"] and len(boxes) == 2:
        middle = _shared(comp, boxes[0], boxes[1])
        if middle is not None:
            return middle  # hard-hearted handout: no double-deal possible
    if not comp["loop"]:
        for box in boxes:  # an end: a box with a side to the ground
            ground = next((s for s, o in links[box] if o is GROUND), None)
            if ground is not None:
                return ground
    return links[boxes[0]][0][0]


def _search_safe(board: _Board, safe: list[str], rng: random.Random, deadline: float) -> str | None:
    """Play every order of the remaining safe lines; the endgame is scored exactly."""
    memo: dict[frozenset[str], int] = {}

    def value() -> int:  # for the player to move
        key = frozenset(board.drawn)
        if key in memo:
            return memo[key]
        _check(deadline)
        moves = board.safe()
        if not moves:
            comps = board.components()
            result = _opener_value(_key(comps)) if comps is not None else 0
        else:
            result = None
            for line in moves:
                board.drawn.add(line)
                try:
                    v = -value()
                finally:
                    board.drawn.discard(line)
                result = v if result is None else max(result, v)
        memo[key] = result
        return result

    scores = {}
    for line in safe:
        board.drawn.add(line)
        try:
            scores[line] = -value()
        finally:
            board.drawn.discard(line)
    best = max(scores.values())
    return rng.choice([line for line, v in scores.items() if v == best])
