"""Shared fixtures: a fresh RoomManager per test, the dummy game, and a WebSocket client."""

import asyncio
import itertools
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from channels.testing import WebsocketCommunicator

from games import registry
from games.constants import EMOJI_PRESETS, PLAYER_COLORS
from rooms import manager as manager_module
from rooms.manager import RoomManager
from tests.dummy_game import DummyGame

ORIGIN = (b"origin", b"http://localhost")


def make_profile(nickname: str = "Sam", **overrides: Any) -> dict[str, Any]:
    """A valid client profile."""
    profile = {
        "id": f"prof-{nickname}",
        "nickname": nickname,
        "emoji": EMOJI_PRESETS[0],
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


@pytest.fixture(autouse=True)
def dummy_game() -> AsyncIterator[DummyGame]:
    game = DummyGame()
    registry.register(game)
    yield game
    registry.unregister(game.id)


@pytest.fixture
async def manager(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[RoomManager]:
    """A fresh RoomManager installed as the process-wide one."""
    fresh = RoomManager()
    monkeypatch.setattr(manager_module, "manager", fresh)
    yield fresh
    tasks = [fresh._cleanup_task]
    tasks += [t for room in fresh.rooms.values() for t in (room.timer_task, room.host_task)]
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
        except Exception:
            pass
