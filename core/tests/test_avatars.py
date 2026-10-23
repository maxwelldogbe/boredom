"""DiceBear avatars: assignment, validation and the room protocol (contract change)."""

import json
import re

import pytest

from games.constants import AVATAR_SEED_PATTERN, AVATAR_STYLES
from rooms.avatars import SeededAvatarRng, assign_avatar, validate_avatar
from rooms.models_types import Avatar, Profile, RoomError
from tests.conftest import make_profile

SEED_RE = re.compile(AVATAR_SEED_PATTERN)
GUEST = Profile(id="prof-123", nickname="Sam", color="#E74C3C")


def assert_valid(avatar: dict | Avatar) -> None:
    data = avatar.to_public() if isinstance(avatar, Avatar) else avatar
    assert set(data) == {"style", "seed"}
    assert data["style"] in AVATAR_STYLES
    assert SEED_RE.fullmatch(data["seed"])


# ----- unit ------------------------------------------------------------------------------


def test_validate_avatar_accepts_valid() -> None:
    assert validate_avatar({"style": "voxel-art", "seed": "a_B-9"}) == Avatar("voxel-art", "a_B-9")


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "voxel-art",
        {"seed": "abc"},
        {"style": "pixel-art", "seed": "abc"},
        {"style": "voxel-art"},
        {"style": "voxel-art", "seed": ""},
        {"style": "voxel-art", "seed": "x" * 33},
        {"style": "voxel-art", "seed": "a b"},
        {"style": "voxel-art", "seed": "https://evil"},
        {"style": "voxel-art", "seed": 1234},
    ],
)
def test_validate_avatar_rejects(raw) -> None:
    with pytest.raises(RoomError) as exc:
        validate_avatar(raw)
    assert exc.value.code == "INVALID_ACTION"


def test_assign_avatar_is_random_valid_and_seeded() -> None:
    a = assign_avatar(GUEST, SeededAvatarRng(1))
    assert_valid(a)
    assert re.fullmatch(r"[0-9a-f]{8}", a.seed)
    assert assign_avatar(GUEST, SeededAvatarRng(1)) == a  # injectable rng is deterministic
    assert assign_avatar(GUEST, SeededAvatarRng(2)) != a


def test_assign_avatar_ignores_guest_supplied_avatar() -> None:
    mine = Avatar("cutouts", "chosen-by-me")
    profile = Profile(id="p", nickname="Sam", color="#E74C3C", avatar=mine)
    assigned = assign_avatar(profile, SeededAvatarRng(1))
    assert assigned != mine
    assert assigned == assign_avatar(GUEST, SeededAvatarRng(1))


def test_seed_never_uses_identifying_values() -> None:
    for i in range(50):
        seed = assign_avatar(GUEST, SeededAvatarRng(i)).seed
        assert "sam" not in seed.lower() and "prof" not in seed and "123" != seed


class _RepeatingRng:
    """Returns the same avatar `repeat` times, then a different one."""

    def __init__(self, repeat: int) -> None:
        self.calls = 0
        self.repeat = repeat

    def choice(self, options):
        return options[0]

    def token_hex(self, nbytes: int) -> str:
        self.calls += 1
        return "aaaaaaaa" if self.calls <= self.repeat else "bbbbbbbb"


def test_assign_avatar_avoids_avatars_taken_in_the_room() -> None:
    taken = {Avatar(AVATAR_STYLES[0], "aaaaaaaa")}
    assert assign_avatar(GUEST, _RepeatingRng(3), taken=taken) == Avatar(
        AVATAR_STYLES[0], "bbbbbbbb"
    )
    with pytest.raises(RuntimeError):
        assign_avatar(GUEST, _RepeatingRng(1000), taken=taken)


# ----- protocol (real /ws/ connections) --------------------------------------------------


async def create(connect, nickname="Host", **profile):
    client = await connect()
    ack = await client.request("room:create", {"profile": make_profile(nickname, **profile)})
    assert ack["ok"], ack
    return client, ack["data"]


async def join(connect, code, nickname, **extra):
    client = await connect()
    profile = make_profile(nickname, **extra.pop("profile", {}))
    ack = await client.request("room:join", {"code": code, "profile": profile, **extra})
    return client, ack


async def test_create_and_join_get_valid_distinct_avatars(connect):
    _, data = await create(connect)
    code = data["room"]["code"]
    for name in ("Ann", "Bob", "Cat"):
        _, ack = await join(connect, code, name)
        assert ack["ok"]
    players = ack["data"]["room"]["players"]
    for p in players:
        assert_valid(p["avatar"])
    keys = {(p["avatar"]["style"], p["avatar"]["seed"]) for p in players}
    assert len(keys) == len(players) == 4


async def test_guest_supplied_avatar_is_ignored(connect):
    mine = {"style": "cutouts", "seed": "picked-by-client"}
    _, data = await create(connect, avatar=mine)
    assert data["room"]["players"][0]["avatar"] != mine
    _, ack = await join(connect, data["room"]["code"], "Ann", profile={"avatar": mine})
    assert ack["ok"] and ack["data"]["room"]["players"][1]["avatar"] != mine


async def test_reconnect_keeps_avatar_and_fresh_join_gets_new_one(connect):
    _, data = await create(connect)
    code = data["room"]["code"]
    ann, ack = await join(connect, code, "Ann")
    first = ack["data"]["room"]["players"][1]["avatar"]
    token = ack["data"]["roomToken"]
    await ann.close()
    _, again = await join(connect, code, "Ann", roomToken=token)
    assert again["ok"] and again["data"]["playerId"] == ack["data"]["playerId"]
    assert again["data"]["room"]["players"][1]["avatar"] == first
    _, fresh = await join(connect, code, "Ann")
    assert fresh["ok"] and fresh["data"]["playerId"] != ack["data"]["playerId"]
    assert fresh["data"]["room"]["players"][2]["avatar"] != first


@pytest.mark.parametrize(
    "bad",
    [{"style": "pixel-art", "seed": "abc"}, {"style": "cutouts", "seed": "no spaces allowed"}],
)
async def test_invalid_avatar_rejected_on_create_and_join(connect, bad):
    client = await connect()
    ack = await client.request("room:create", {"profile": make_profile("Sam", avatar=bad)})
    assert ack["error"]["code"] == "INVALID_ACTION"
    _, data = await create(connect)
    _, ack = await join(connect, data["room"]["code"], "Ann", profile={"avatar": bad})
    assert ack["error"]["code"] == "INVALID_ACTION"


async def test_room_state_has_no_emoji_and_no_urls(connect):
    host, data = await create(connect, emoji="😀")
    await join(connect, data["room"]["code"], "Ann", profile={"emoji": "🦊"})
    state = await host.wait_push("room:state", lambda d: len(d["players"]) == 2)
    blob = json.dumps(state)
    assert "emoji" not in blob
    assert "http" not in blob and "dicebear" not in blob and "/svg" not in blob


async def test_manager_uses_injected_avatar_rng(manager, connect):
    manager.avatar_rng = SeededAvatarRng(7)
    _, data = await create(connect)
    expected = assign_avatar(GUEST, SeededAvatarRng(7)).to_public()
    assert data["room"]["players"][0]["avatar"] == expected


def test_assign_avatar_keeps_a_registered_accounts_saved_avatar() -> None:
    saved = Avatar(style="cutouts", seed="saved1")
    account = Profile(id="account-1", nickname="Sam", color="#E74C3C", avatar=saved, user_id=1)
    assert assign_avatar(account, SeededAvatarRng(1)) == saved
    assert assign_avatar(account, SeededAvatarRng(1), taken={saved}) == saved  # kept forever
