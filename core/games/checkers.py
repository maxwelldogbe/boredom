"""American checkers as a MatchEngine, run in matches and a bracket by games/series.py.

8x8 board, dark squares only ((row + col) odd). Seat 1 (red) starts on rows 5-7 and moves up
(toward row 0); seat 2 (blue) starts on rows 0-2 and moves down. Men step one square
diagonally forward; kings one square in any diagonal direction. Capturing is mandatory.
Each hop is its own action: after a capture the same piece must keep capturing while it can
(the player keeps the turn), except that a man reaching the far row is crowned and the turn
ends at once. A player with no pieces or no legal move loses. CHECKERS_DRAW_PLIES plies in a
row without a capture or a man move draw the game.

Settings: `flyingKings` (kings move and capture at any distance) and `backwardCapture` (men
may also capture backward).
"""

import random
from dataclasses import dataclass, field
from typing import Any

from games.base import GameError, GameEvent
from games.constants import CHECKERS_DRAW_PLIES, CHECKERS_TURN_MS
from games.match_engine import MatchEngine, Outcome
from games.series import SeriesGame

SIZE = 8
DIAGONALS = ((-1, -1), (-1, 1), (1, -1), (1, 1))

Square = tuple[int, int]
Piece = dict[str, Any]  # {"seat": 1 | 2, "king": bool}
Move = dict[str, Any]  # {"from": [r, c], "to": [r, c], "captures": [[r, c]]}


def initial_board() -> list[list[Piece | None]]:
    board: list[list[Piece | None]] = [[None] * SIZE for _ in range(SIZE)]
    for r in range(SIZE):
        for c in range(SIZE):
            if (r + c) % 2 == 1 and r != 3 and r != 4:
                board[r][c] = {"seat": 2 if r < 3 else 1, "king": False}
    return board


def forward(seat: int) -> int:
    """Row direction a man of `seat` moves in."""
    return -1 if seat == 1 else 1


def on_board(r: int, c: int) -> bool:
    return 0 <= r < SIZE and 0 <= c < SIZE


@dataclass
class CheckersState:
    a: str  # seat 1, red
    b: str  # seat 2, blue
    first: str
    turn: str
    flying_kings: bool
    backward_capture: bool
    board: list[list[Piece | None]] = field(default_factory=initial_board)
    forced: Square | None = None  # the piece that must continue a multi-jump
    quiet_plies: int = 0  # plies in a row without a capture or a man move
    deadline: float | None = None
    last_move: dict[str, Any] | None = None
    winner: str | None = None
    draw: bool = False

    def seat_of(self, player_id: str) -> int:
        return 1 if player_id == self.a else 2

    def player_of(self, seat: int) -> str:
        return self.a if seat == 1 else self.b


def piece_captures(state: CheckersState, r: int, c: int) -> list[Move]:
    """Capturing hops for the piece on (r, c)."""
    piece = state.board[r][c]
    assert piece is not None
    moves: list[Move] = []
    for dr, dc in DIAGONALS:
        if not piece["king"] and dr != forward(piece["seat"]) and not state.backward_capture:
            continue
        reach = SIZE if piece["king"] and state.flying_kings else 1
        mr, mc, steps = r + dr, c + dc, 1
        while on_board(mr, mc) and state.board[mr][mc] is None and steps < reach:
            mr, mc, steps = mr + dr, mc + dc, steps + 1
        if not on_board(mr, mc):
            continue
        target = state.board[mr][mc]
        if target is None or target["seat"] == piece["seat"]:
            continue
        lr, lc = mr + dr, mc + dc
        landings = 0
        while on_board(lr, lc) and state.board[lr][lc] is None and landings < reach:
            moves.append({"from": [r, c], "to": [lr, lc], "captures": [[mr, mc]]})
            lr, lc, landings = lr + dr, lc + dc, landings + 1
    return moves


def piece_steps(state: CheckersState, r: int, c: int) -> list[Move]:
    """Non-capturing moves for the piece on (r, c)."""
    piece = state.board[r][c]
    assert piece is not None
    moves: list[Move] = []
    for dr, dc in DIAGONALS:
        if not piece["king"] and dr != forward(piece["seat"]):
            continue
        reach = SIZE if piece["king"] and state.flying_kings else 1
        tr, tc, steps = r + dr, c + dc, 0
        while on_board(tr, tc) and state.board[tr][tc] is None and steps < reach:
            moves.append({"from": [r, c], "to": [tr, tc], "captures": []})
            tr, tc, steps = tr + dr, tc + dc, steps + 1
    return moves


def legal_moves(state: CheckersState, seat: int) -> list[Move]:
    """Every legal move for `seat`, with mandatory capture and a continuing jump applied."""
    if state.forced is not None:
        return piece_captures(state, *state.forced)
    squares = [
        (r, c)
        for r in range(SIZE)
        for c in range(SIZE)
        if (p := state.board[r][c]) is not None and p["seat"] == seat
    ]
    captures = [m for r, c in squares for m in piece_captures(state, r, c)]
    return captures or [m for r, c in squares for m in piece_steps(state, r, c)]


class CheckersEngine(MatchEngine):
    def init(self, player_a, player_b, settings, rng, first_mover) -> CheckersState:
        return CheckersState(
            player_a,
            player_b,
            first_mover,
            first_mover,
            settings["flyingKings"],
            settings["backwardCapture"],
        )

    def apply(self, state: CheckersState, player_id, action, now) -> tuple[Any, list[GameEvent]]:
        if action.get("type") != "move":
            raise GameError("INVALID_ACTION", "Unknown action.")
        if self.status(state)[0] != "ongoing":
            raise GameError("INVALID_ACTION", "The game is over.")
        if player_id != state.turn:
            raise GameError("NOT_YOUR_TURN", "Wait for your turn.")
        src, dst = action.get("from"), action.get("to")
        seat = state.seat_of(player_id)
        move = next(
            (m for m in legal_moves(state, seat) if m["from"] == src and m["to"] == dst), None
        )
        if move is None:
            raise GameError("INVALID_ACTION", "That move is not allowed.")
        (fr, fc), (tr, tc) = move["from"], move["to"]
        piece = state.board[fr][fc]
        assert piece is not None
        was_man = not piece["king"]
        state.board[fr][fc], state.board[tr][tc] = None, piece
        for cr, cc in move["captures"]:
            state.board[cr][cc] = None
        crowned = was_man and tr == (0 if seat == 1 else SIZE - 1)
        if crowned:
            piece["king"] = True
        state.quiet_plies = 0 if move["captures"] or was_man else state.quiet_plies + 1
        state.last_move = {**move, "playerId": player_id, "crowned": crowned}
        state.forced = None
        if move["captures"] and not crowned and piece_captures(state, tr, tc):
            state.forced = (tr, tc)  # the same player keeps the turn
        else:
            state.turn = state.player_of(3 - seat)
            if not legal_moves(state, 3 - seat):
                state.winner = player_id
            elif state.quiet_plies >= CHECKERS_DRAW_PLIES:
                state.draw = True
        ongoing = self.status(state)[0] == "ongoing"
        state.deadline = now + CHECKERS_TURN_MS if ongoing else None
        return state, []

    def tick(self, state: CheckersState, now) -> tuple[Any, list[GameEvent]]:
        if state.deadline is None and self.status(state)[0] == "ongoing":
            state.deadline = now + CHECKERS_TURN_MS
        return state, []

    def awaiting(self, state: CheckersState) -> list[str]:
        return [state.turn] if self.status(state)[0] == "ongoing" else []

    def random_action(self, state: CheckersState, player_id, rng: random.Random) -> dict[str, Any]:
        move = rng.choice(legal_moves(state, state.seat_of(player_id)))
        return {"type": "move", "from": move["from"], "to": move["to"]}

    def public_view(self, state: CheckersState) -> dict[str, Any]:
        ongoing = self.status(state)[0] == "ongoing"
        return {
            "board": [[dict(p) if p else None for p in row] for row in state.board],
            "seats": {state.a: 1, state.b: 2},
            "firstMover": state.first,
            "turn": state.turn if ongoing else None,
            "turnDeadline": state.deadline,
            "forcedPiece": list(state.forced) if state.forced else None,
            "lastMove": state.last_move,
            "quietPlies": state.quiet_plies,
            "drawPlies": CHECKERS_DRAW_PLIES,
            "flyingKings": state.flying_kings,
            "backwardCapture": state.backward_capture,
            "winner": state.winner,
            "draw": state.draw,
        }

    def view_for(self, state: CheckersState, player_id) -> dict[str, Any]:
        view = self.public_view(state)
        if view["turn"] != player_id:
            return {**view, "isYourTurn": False}
        return {
            **view,
            "isYourTurn": True,
            "legalMoves": legal_moves(state, state.seat_of(player_id)),
        }

    def status(self, state: CheckersState) -> Outcome:
        if state.winner is not None:
            return "winner", state.winner
        return ("draw", None) if state.draw else ("ongoing", None)

    def next_deadline(self, state: CheckersState) -> float | None:
        return state.deadline


class Checkers(SeriesGame):
    id = "checkers"
    name = "Checkers"
    default_settings: dict[str, Any] = {"bestOf": 1, "flyingKings": False, "backwardCapture": False}
    engine = CheckersEngine()

    def validate_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = super().validate_settings(settings)
        if merged["bestOf"] not in (1, 3):
            raise GameError("INVALID_ACTION", "bestOf must be 1 or 3.")
        for key in ("flyingKings", "backwardCapture"):
            if type(merged[key]) is not bool:
                raise GameError("INVALID_ACTION", f"{key} must be true or false.")
        return merged
