"""Nemesis data never reaches the room WebSocket, and guests get nothing from the wallet API."""

import json

import pytest
from channels.db import database_sync_to_async

from accounts.tokens import issue_token
from nemesis import ledger
from nemesis.models import LedgerAccount, NemesisProfile
from tests.conftest import make_profile
from tests.nemesis_helpers import account_user

pytestmark = pytest.mark.django_db(transaction=True)
FORBIDDEN_WORDS = ("nemesis", "balance", "wallet", "held", "idstate", "deposit", "withdraw")
Kind = LedgerAccount.Kind


@database_sync_to_async
def nemesis_player() -> str:
    user = account_user(eligible=True)
    NemesisProfile.objects.create(user=user, active=True)
    ledger.post_transaction(
        "deposit",
        f"seed:{user.pk}",
        [(ledger.account(Kind.EXTERNAL), -98765), (ledger.account(Kind.USER, user), 98765)],
    )
    return issue_token(user.pk)


async def test_room_messages_carry_no_nemesis_data(connect, settings) -> None:
    settings.NEMESIS_ENABLED = True
    host = await connect()
    ack = await host.request("room:create", {"authToken": await nemesis_player()})
    assert ack["ok"], ack
    other = await connect()
    joined = await other.request(
        "room:join",
        {"code": ack["data"]["room"]["code"], "authToken": await nemesis_player()},
    )
    guest = await connect()
    await guest.request(
        "room:join", {"code": ack["data"]["room"]["code"], "profile": make_profile("Gus")}
    )
    await host.wait_push("room:state", lambda d: len(d["players"]) == 3)
    seen = json.dumps([ack, joined, *host.pushes, *other.pushes, *guest.pushes]).lower()
    for word in FORBIDDEN_WORDS:
        assert word not in seen, word
    assert "98765" not in seen


def test_guests_get_nothing(client, settings) -> None:
    settings.NEMESIS_ENABLED = True
    for path in ("/api/nemesis/status", "/api/wallet", "/api/wallet/deposits"):
        assert client.get(path).status_code == 401
