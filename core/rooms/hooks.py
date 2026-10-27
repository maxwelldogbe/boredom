"""Extension seam for the rest of the server: room moments and finished games.

Two consumers plug in here:
- account stats: registered players' PlayerStats, updated in a background task;
- the activity recorder (analytics), which queues records and returns at once.
Neither can hold up the room lock or break a game: failures are logged.
"""

import asyncio
import logging
from dataclasses import dataclass

from analytics.recorder import SeatRecord, SessionRecord, recorder
from games.scoring import ScoredResult
from rooms.models_types import Player, Room

logger = logging.getLogger("rooms.hooks")

_pending: set[asyncio.Task[None]] = set()


@dataclass(frozen=True)
class GameRecord:
    """A snapshot of a game when it ends. `results` is None when it was abandoned."""

    room_code: str
    game_id: str
    settings: dict
    started_at_ms: float
    ended_at_ms: float
    seats: tuple[Player, ...]
    results: tuple[ScoredResult, ...] | None
    forfeited: frozenset[str] = frozenset()  # seats that quit, left or timed out offline

    @property
    def accounts(self) -> dict[str, int]:
        """Seat id -> user id for every registered seat."""
        return {p.id: p.user_id for p in self.seats if p.user_id is not None}


def game_record(
    room: Room, game_id: str, now: float, results: list[ScoredResult] | None
) -> GameRecord:
    """Snapshot `room` (including seats that left mid-game) as its game ends."""
    return GameRecord(
        room_code=room.code,
        game_id=game_id,
        settings=dict(room.settings),
        started_at_ms=room.game_started_at if room.game_started_at is not None else now,
        ended_at_ms=now,
        seats=tuple(room.players),
        results=tuple(results) if results is not None else None,
        forfeited=frozenset(room.forfeits),
    )


def on_room_event(kind: str, room_code: str, player: Player) -> None:
    """room_created, room_joined (new seats only) or room_left."""
    recorder.record_event(
        kind, user_id=player.user_id, guest_key=player.guest_key, room_code=room_code
    )


def on_game_started(room_code: str, game_id: str) -> None:
    recorder.record_event("game_started", room_code=room_code, game_id=game_id)


def on_game_finished(game: GameRecord) -> None:
    """Called once per completed game, after the scoreboard and gameOver went out."""
    results = game.results or ()
    logger.info("Game finished: room=%s game=%s results=%s", game.room_code, game.game_id, results)
    by_seat = {r["player_id"]: r for r in results}
    seats = []
    for player in game.seats:
        result = by_seat.get(player.id)
        seats.append(
            SeatRecord(
                user_id=player.user_id,
                guest_key=player.guest_key,
                nickname=player.nickname,
                left_early=player.left or not player.online or player.id in game.forfeited,
                placement=result["placement"] if result else None,
                raw_score=float(result["score"]) if result else None,
                points=result["points"] if result else None,
            )
        )
    _record(game, "completed", seats, "game_finished")

    accounts = game.accounts
    outcomes = {
        accounts[r["player_id"]]: r["placement"] == 1 for r in results if r["player_id"] in accounts
    }
    if outcomes:
        task = asyncio.get_running_loop().create_task(_record_stats(game, outcomes))
        _pending.add(task)
        task.add_done_callback(_pending.discard)


def on_game_abandoned(game: GameRecord) -> None:
    """Called when a room is removed mid-game: no placements, nobody wins."""
    logger.info("Game abandoned: room=%s game=%s", game.room_code, game.game_id)
    seats = [
        SeatRecord(
            user_id=p.user_id,
            guest_key=p.guest_key,
            nickname=p.nickname,
            left_early=p.left or p.id in game.forfeited,
        )
        for p in game.seats
    ]
    _record(game, "abandoned", seats, "game_abandoned")


def _record(game: GameRecord, status: str, seats: list[SeatRecord], kind: str) -> None:
    recorder.record_session(
        SessionRecord(
            game_id=game.game_id,
            room_code=game.room_code,
            settings=game.settings,
            status=status,
            started_at_ms=game.started_at_ms,
            ended_at_ms=game.ended_at_ms,
            seats=tuple(seats),
        )
    )
    recorder.record_event(
        kind,
        room_code=game.room_code,
        game_id=game.game_id,
        meta={
            "players": len(seats),
            "seconds": round((game.ended_at_ms - game.started_at_ms) / 1000),
        },
    )


async def _record_stats(game: GameRecord, outcomes: dict[int, bool]) -> None:
    from accounts.rooms import record_results  # needs the Django app registry

    try:
        await record_results(game.game_id, outcomes)
    except Exception:
        logger.exception("Stats update failed: room=%s game=%s", game.room_code, game.game_id)


async def drain() -> None:
    """Wait for stats writes and activity records still in flight (tests and shutdown)."""
    while _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)
    await recorder.drain()
