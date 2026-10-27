"""Shared fixtures: a fresh RoomManager per test, the dummy game, and a WebSocket client."""

import asyncio
import itertools
import json
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import pytest
from channels.testing import WebsocketCommunicator

from analytics.recorder import Recorder, recorder
from games import registry
from games.constants import PLAYER_COLORS
from rooms import manager as manager_module
from rooms.manager import RoomManager
from tests.dummy_game import DummyGame

pytest_plugins = ["tests.dashboard_data"]

ORIGIN = (b"origin", b"http://localhost")


def make_profile(nickname: str = "Sam", **overrides: Any) -> dict[str, Any]:
    """A valid client profile."""
    profile = {
        "id": f"prof-{nickname}",
        "nickname": nickname,
        "color": PLAYER_COLORS[0],
        "type": "guest",
    }
    profile.update(overrides)
    return profile


class WsClient:
    """Test client speaking the Boredom protocol; keeps pushes for later inspection."""

    def __init__(self, communicator: WebsocketCommunicator) -> None:
        self.comm = communicator
        self.ids = itertools.count(1)
        self.pushes: list[dict[str, Any]] = []
        self.player_id: str | None = None
        self.token: str | None = None

    async def request(self, type_: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a request and return its ack, buffering any pushes received meanwhile."""
        request_id = next(self.ids)
        message = {"id": request_id, "type": type_, "payload": payload or {}}
        await self.comm.send_to(text_data=json.dumps(message))
        return await self.ack(request_id)

    async def ack(self, request_id: int) -> dict[str, Any]:
        while True:
            message = await self.recv()
            if message.get("type") == "ack" and message.get("id") == request_id:
                if message["ok"] and "playerId" in message["data"]:
                    self.player_id = message["data"]["playerId"]
                    self.token = message["data"]["roomToken"]
                return message
            self.pushes.append(message)

    async def recv(self, timeout: float = 2) -> dict[str, Any]:
        return json.loads(await self.comm.receive_from(timeout=timeout))

    async def wait_push(
        self, type_: str, where: Callable[[dict[str, Any]], bool] = lambda d: True, timeout=2.0
    ) -> dict[str, Any]:
        """Return (and consume) the first push of `type_` whose data matches `where`."""
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while True:
            for i, push in enumerate(self.pushes):
                if push["type"] == type_ and where(push["data"]):
                    return self.pushes.pop(i)["data"]
            self.pushes.append(await self.recv(timeout=max(0.01, end - loop.time())))

    def latest(self, type_: str) -> dict[str, Any] | None:
        """Most recent buffered push of `type_`, without consuming it."""
        found = [p["data"] for p in self.pushes if p["type"] == type_]
        return found[-1] if found else None

    async def drain(self) -> None:
        """Buffer everything already delivered."""
        while not await self.comm.receive_nothing(timeout=0.05):
            self.pushes.append(await self.recv())

    async def close(self) -> None:
        await self.comm.disconnect()


class NoQuota:
    """Stands in for GuestQuotaStore in tests without the database."""

    async def read(self, keys: list[str], now: float) -> dict:
        return {}

    async def count(self, keys: list[str], now: float) -> dict:
        return {}


@pytest.fixture(scope="session")
def django_db_modify_db_settings(django_db_modify_db_settings_parallel_suffix: None) -> None:
    """Test SQLite as a file, not in memory: in-memory connections are never closed, so one
    opened by a WebSocket's database thread would outlive its test and trip later tests.
    Durability is pointless for a throwaway test database, so skip fsync."""
    from django.conf import settings

    db = settings.DATABASES["default"]
    if db["ENGINE"] == "django.db.backends.sqlite3":
        db["TEST"] = {**db.get("TEST", {}), "NAME": str(settings.BASE_DIR / "test_db.sqlite3")}
        db["OPTIONS"] = {
            **db.get("OPTIONS", {}),
            "init_command": "PRAGMA synchronous=OFF; PRAGMA journal_mode=MEMORY;",
        }


@pytest.fixture(autouse=True)
def no_activity_recording(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Activity recording writes to the database; tests opt in with `recording`."""
    monkeypatch.setattr(recorder, "enabled", False)
    yield
    recorder.stop()


@pytest.fixture
def recording(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """Turn activity recording on (needs database access)."""
    monkeypatch.setattr(recorder, "enabled", True)
    return recorder


@pytest.fixture(autouse=True)
def fast_password_hashing(settings: Any) -> None:
    """Real hashers are deliberately slow; tests only need hashing to work."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def dummy_game() -> AsyncIterator[DummyGame]:
    game = DummyGame()
    registry.register(game)
    yield game
    registry.unregister(game.id)


@pytest.fixture
async def manager(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> AsyncIterator[RoomManager]:
    """A fresh RoomManager installed as the process-wide one.

    Without database access the guest quota is skipped (as if nobody had played yet).
    """
    fresh = RoomManager()
    if request.node.get_closest_marker("django_db") is None:
        fresh.quota = NoQuota()  # type: ignore[assignment]
    monkeypatch.setattr(manager_module, "manager", fresh)
    yield fresh
    tasks = [fresh._cleanup_task, *fresh.social.tasks()]
    for room in fresh.rooms.values():
        tasks += [room.timer_task, room.host_task]
        tasks += [*room.notice_tasks.values(), *room.forfeit_tasks.values()]
    for task in tasks:
        if task is not None:
            task.cancel()


@pytest.fixture
async def connect(manager: RoomManager) -> AsyncIterator[Callable[[], Any]]:
    """Factory opening WebSocket clients to /ws/; all are closed after the test."""
    from config.asgi import application

    clients: list[WsClient] = []

    async def _connect() -> WsClient:
        comm = WebsocketCommunicator(application, "/ws/", headers=[ORIGIN])
        connected, _ = await comm.connect()
        assert connected
        client = WsClient(comm)
        clients.append(client)
        return client

    yield _connect
    for client in clients:
        try:
            await client.close()
        except (Exception, asyncio.CancelledError):
            pass  # a failed test may leave the app task already cancelled
