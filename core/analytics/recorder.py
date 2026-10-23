"""Fire-and-forget activity recording for the dashboard.

`record_event` and `record_session` return immediately: they put the record on one bounded
in-memory queue that one consumer task drains into the database. They never raise into the
caller, never wait on the database, and drop (and log) records when the queue is full.

The consumer starts on the event loop of the ASGI app the first time it is needed (the
WebSocket consumer starts it on connect) together with the daily retention task. Callers in a
thread without an event loop (sync HTTP views) hand records to that loop; if it is not running
yet, the record is written directly in the calling thread, which is a request thread and never
a room lock.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from analytics.models import ActivityEvent, GameParticipation, GameSession
from analytics.retention import prune_events

logger = logging.getLogger("analytics")

QUEUE_MAX = 1000
RETENTION_INTERVAL_S = 24 * 60 * 60
META_MAX_KEYS = 8


@dataclass(frozen=True)
class SeatRecord:
    """One seat in a finished or abandoned game. `placement` is None when abandoned."""

    user_id: int | None
    guest_key: str
    nickname: str
    left_early: bool
    placement: int | None = None
    raw_score: float | None = None
    points: float | None = None


@dataclass(frozen=True)
class SessionRecord:
    game_id: str
    room_code: str
    settings: dict[str, Any]
    status: str  # GameSession.Status
    started_at_ms: float
    ended_at_ms: float
    seats: tuple[SeatRecord, ...]


@dataclass(frozen=True)
class EventRecord:
    kind: str
    occurred_at: datetime
    user_id: int | None = None
    guest_key: str = ""
    room_code: str = ""
    game_id: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


def _from_ms(ms: float) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def _existing_users(user_ids: set[int]) -> set[int]:
    if not user_ids:
        return set()
    return set(User.objects.filter(pk__in=user_ids).values_list("pk", flat=True))


def write_record(record: EventRecord | SessionRecord) -> None:
    """Store one record (sync; runs in a database thread). Deleted accounts become null."""
    if isinstance(record, EventRecord):
        user_id = record.user_id
        if user_id is not None and not _existing_users({user_id}):
            user_id = None
        ActivityEvent.objects.create(
            kind=record.kind,
            occurred_at=record.occurred_at,
            user_id=user_id,
            guest_key=record.guest_key if user_id is None else "",
            room_code=record.room_code,
            game_id=record.game_id,
            meta=record.meta,
        )
        return
    started, ended = _from_ms(record.started_at_ms), _from_ms(record.ended_at_ms)
    completed = record.status == GameSession.Status.COMPLETED
    with transaction.atomic():
        existing = _existing_users({s.user_id for s in record.seats if s.user_id is not None})
        session = GameSession.objects.create(
            game_id=record.game_id,
            room_code=record.room_code,
            settings=record.settings,
            status=record.status,
            started_at=started,
            ended_at=ended,
            duration_seconds=max(0, round((record.ended_at_ms - record.started_at_ms) / 1000)),
            player_count=len(record.seats),
        )
        GameParticipation.objects.bulk_create(
            GameParticipation(
                session=session,
                user_id=seat.user_id if seat.user_id in existing else None,
                guest_key="" if seat.user_id is not None else seat.guest_key,
                player_type=(
                    GameParticipation.PlayerType.REGISTERED
                    if seat.user_id is not None
                    else GameParticipation.PlayerType.GUEST
                ),
                nickname=seat.nickname,
                placement=seat.placement if completed else None,
                raw_score=seat.raw_score if completed else None,
                session_points=(
                    Decimal(str(seat.points)) if completed and seat.points is not None else None
                ),
                is_win=completed and seat.placement == 1,
                left_early=seat.left_early,
            )
            for seat in record.seats
        )


class Recorder:
    """The process-wide activity queue and its consumer task."""

    def __init__(self, maxsize: int = QUEUE_MAX) -> None:
        self.enabled = True
        self.maxsize = maxsize
        self.dropped = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[EventRecord | SessionRecord] | None = None
        self._tasks: list[asyncio.Task[None]] = []

    # ----- public API (never raises) --------------------------------------------------

    def record_event(
        self,
        kind: str,
        *,
        user_id: int | None = None,
        guest_key: str = "",
        room_code: str = "",
        game_id: str = "",
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Queue an ActivityEvent. `meta` must be small and secret-free."""
        try:
            small = dict(list((meta or {}).items())[:META_MAX_KEYS])
            record = EventRecord(
                kind, timezone.now(), user_id, guest_key, room_code, game_id, small
            )
            self._submit(record)
        except Exception:
            logger.exception("Could not queue activity event %s", kind)

    def record_session(self, session: SessionRecord) -> None:
        """Queue a finished or abandoned game session with its participations."""
        try:
            self._submit(session)
        except Exception:
            logger.exception("Could not queue game session %s", session.game_id)

    def start(self) -> None:
        """Start the consumer and retention tasks on the running loop (idempotent)."""
        if not self.enabled:
            return
        loop = asyncio.get_running_loop()
        if self._loop is loop and all(not t.done() for t in self._tasks):
            return
        self.stop()
        self._loop = loop
        self._queue = asyncio.Queue(maxsize=self.maxsize)
        self._tasks = [loop.create_task(self._consume()), loop.create_task(self._retention())]

    def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks, self._loop, self._queue = [], None, None

    async def drain(self) -> None:
        """Wait until every queued record has been written (tests and shutdown)."""
        if self._queue is not None:
            await self._queue.join()

    # ----- internals ------------------------------------------------------------------

    def _submit(self, record: EventRecord | SessionRecord) -> None:
        if not self.enabled:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is not None:
            self.start()
            self._put(record)
        elif self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._put, record)
        else:
            try:
                write_record(record)
            except Exception:
                logger.exception("Activity write failed")

    def _put(self, record: EventRecord | SessionRecord) -> None:
        if self._queue is None:
            return
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            self.dropped += 1
            kind = getattr(record, "kind", "session")
            logger.warning("Activity queue full: dropped a %s record", kind)

    async def _consume(self) -> None:
        queue = self._queue
        assert queue is not None
        while True:
            record = await queue.get()
            try:
                await database_sync_to_async(write_record)(record)
            except Exception:
                logger.exception("Activity write failed")
            finally:
                queue.task_done()

    async def _retention(self) -> None:
        while True:
            try:
                removed = await database_sync_to_async(prune_events)()
                if removed:
                    logger.info("Pruned %s old activity events", removed)
            except Exception:
                logger.exception("Activity retention failed")
            await asyncio.sleep(RETENTION_INTERVAL_S)


recorder = Recorder()
