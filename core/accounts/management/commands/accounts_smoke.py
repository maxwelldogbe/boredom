"""`python manage.py accounts_smoke`: register, log in and join rooms end to end.

Runs against the real ASGI app and the configured database (run `migrate` first). It uses a
throwaway account and deletes it at the end, even after a failure.
"""

import asyncio
import json
import secrets
from typing import Any

from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.test import Client

from games.constants import PLAYER_COLORS

PASSWORD = "smoke-" + secrets.token_hex(8)
AVATAR = {"style": "cutouts", "seed": "smoke123"}


class Check:
    """Collects PASS / FAIL lines."""

    def __init__(self, write) -> None:
        self.write = write
        self.failures = 0

    def __call__(self, ok: bool, label: str) -> None:
        self.write(f"{'PASS' if ok else 'FAIL'}  {label}")
        self.failures += not ok


class Command(BaseCommand):
    help = "End-to-end check of accounts: register, login, me, and WebSocket joins."

    def handle(self, *args: Any, **options: Any) -> None:
        check = Check(self.stdout.write)
        username = "smoke_" + secrets.token_hex(4)
        try:
            token = self._http(check, username)
            if token:
                asyncio.run(self._ws(check, token))
        finally:
            User.objects.filter(username=username).delete()
        if check.failures:
            raise CommandError(f"{check.failures} check(s) failed.")
        self.stdout.write(self.style.SUCCESS("All account checks passed."))

    def _http(self, check: Check, username: str) -> str | None:
        client = Client(HTTP_HOST="localhost")

        def post(path: str, body: dict, **extra: Any):
            return client.post(path, json.dumps(body), content_type="application/json", **extra)

        profile = {"nickname": "Smoke", "color": PLAYER_COLORS[3], "avatar": AVATAR}
        reg = post(
            "/api/auth/register", {"username": username, "password": PASSWORD, "profile": profile}
        )
        check(reg.status_code == 201, "register returns 201 with a token")
        if reg.status_code != 201:
            self.stdout.write(f"      {reg.content.decode()[:200]}")
            return None
        check(reg.json()["profile"]["avatar"] == AVATAR, "register keeps the guest avatar")
        again = post(
            "/api/auth/register",
            {"username": username.upper(), "password": PASSWORD, "profile": profile},
        )
        check(again.status_code == 409, "a taken username gives 409 USERNAME_TAKEN")
        bad = post("/api/auth/login", {"username": username, "password": "wrong-" + PASSWORD})
        check(bad.status_code == 401, "a wrong password gives 401")
        login = post("/api/auth/login", {"username": username, "password": PASSWORD})
        check(login.status_code == 200 and "token" in login.json(), "login returns a token")
        token = login.json().get("token") if login.status_code == 200 else None
        me = client.get("/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        check(
            me.status_code == 200 and me.json()["profile"]["nickname"] == "Smoke",
            "me returns the profile",
        )
        return token

    async def _ws(self, check: Check, token: str) -> None:
        from config.asgi import application

        async def connect() -> WebsocketCommunicator:
            comm = WebsocketCommunicator(
                application, "/ws/", headers=[(b"origin", b"http://localhost")]
            )
            connected, _ = await comm.connect()
            check(connected, "WebSocket connects")
            return comm

        async def request(comm: WebsocketCommunicator, type_: str, payload: dict) -> dict:
            await comm.send_to(text_data=json.dumps({"id": 1, "type": type_, "payload": payload}))
            while True:
                message = json.loads(await comm.receive_from(timeout=5))
                if message.get("type") == "ack":
                    return message

        guest_profile = {"id": "smoke-guest", "nickname": "Guest", "color": PLAYER_COLORS[0]}
        host, second, guest = await connect(), await connect(), await connect()
        try:
            created = await request(
                host, "room:create", {"authToken": token, "profile": guest_profile}
            )
            data = created.get("data", {})
            me = next(
                (
                    p
                    for p in data.get("room", {}).get("players", [])
                    if p["id"] == data.get("playerId")
                ),
                {},
            )
            check(
                created.get("ok") and me.get("type") == "registered",
                "room:create with authToken seats a registered player",
            )
            check(
                me.get("nickname") == "Smoke" and me.get("avatar") == AVATAR,
                "the seat uses the saved profile and avatar",
            )
            check(
                "profileId" not in json.dumps(data) and token not in json.dumps(data),
                "room:state has no profileId or token",
            )
            code = data.get("room", {}).get("code", "")
            joined = await request(
                second, "room:join", {"code": code, "authToken": token, "profile": guest_profile}
            )
            check(
                joined.get("ok") and joined["data"]["playerId"] == data.get("playerId"),
                "joining again with the same account reclaims the seat",
            )
            stale = await request(
                guest, "room:join", {"code": code, "authToken": "stale", "profile": guest_profile}
            )
            check(
                stale.get("ok") and stale["data"].get("authStatus") == "invalid",
                "an invalid authToken joins as a guest with authStatus invalid",
            )
        finally:
            for comm in (host, second, guest):
                await comm.disconnect()
