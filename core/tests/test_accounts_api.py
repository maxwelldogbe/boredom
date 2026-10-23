"""Account HTTP API: register, login, me, profile edit, deletion, tokens and rate limits."""

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client

from accounts import ratelimit, services
from accounts.models import PlayerStats, Profile
from accounts.tokens import issue_token, user_id_from_token
from games.constants import (
    AUTH_RATE_LIMIT_PER_MIN,
    AUTH_TOKEN_DAYS,
    AVATAR_SEED_PATTERN,
    AVATAR_STYLES,
    PLAYER_COLORS,
    STATS_MAX_IMPORT_GAMES,
)

pytestmark = pytest.mark.django_db

PASSWORD = "correct horse battery"
AVATAR = {"style": "cutouts", "seed": "9c41e07b"}


@pytest.fixture(autouse=True)
def reset_limits() -> None:
    ratelimit.register_limiter.reset()
    ratelimit.login_limiter.reset()


def call(
    client: Client, method: str, path: str, body: Any = None, token: str | None = None, **extra
):
    headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
    data = json.dumps(body) if body is not None else ""
    return getattr(client, method)(
        f"/api/auth/{path}", data=data, content_type="application/json", **headers, **extra
    )


def register_body(username: str = "sam_1", **profile: Any) -> dict[str, Any]:
    base = {"nickname": "Sam", "color": PLAYER_COLORS[2], "avatar": AVATAR}
    base.update(profile)
    return {"username": username, "password": PASSWORD, "profile": base}


def register(client: Client, username: str = "sam_1", **profile: Any) -> dict[str, Any]:
    response = call(client, "post", "register", register_body(username, **profile))
    assert response.status_code == 201, response.json()
    return response.json()


def error(response) -> dict[str, Any]:
    return response.json()["error"]


# Register


def test_register_creates_account_and_returns_token(client: Client) -> None:
    data = register(client)
    assert set(data) == {"token", "profile"}
    assert data["profile"]["username"] == "sam_1"
    assert data["profile"]["nickname"] == "Sam"
    assert data["profile"]["color"] == PLAYER_COLORS[2]
    assert data["profile"]["avatar"] == AVATAR
    assert data["profile"]["type"] == "registered"
    user = User.objects.get(username="sam_1")
    assert user_id_from_token(data["token"]) == user.pk
    assert user.check_password(PASSWORD)
    assert user.password != PASSWORD


def test_register_never_creates_staff(client: Client) -> None:
    register(client)
    user = User.objects.get()
    assert not user.is_staff and not user.is_superuser


def test_register_username_taken_ignores_case(client: Client) -> None:
    register(client, "Sam_1")
    response = call(client, "post", "register", register_body("sam_1"))
    assert response.status_code == 409
    assert error(response)["code"] == "USERNAME_TAKEN"
    assert User.objects.count() == 1


@pytest.mark.parametrize("password", ["short1!", "password123", "12345678901", "sam_1sam"])
def test_register_weak_password(client: Client, password: str) -> None:
    body = register_body() | {"password": password}
    response = call(client, "post", "register", body)
    assert response.status_code == 400
    assert error(response)["code"] == "INVALID_INPUT"
    assert "password" in error(response)["fields"]
    assert not User.objects.exists()


@pytest.mark.parametrize("username", ["ab", "x" * 21, "sam smith", "sam-1", "", None, 5])
def test_register_bad_username(client: Client, username: Any) -> None:
    response = call(client, "post", "register", register_body() | {"username": username})
    assert response.status_code == 400
    assert set(error(response)["fields"]) == {"username"}


def test_register_validates_profile_like_rooms(client: Client) -> None:
    body = register_body(nickname="x" * 40, color="#000000")
    response = call(client, "post", "register", body)
    assert response.status_code == 400
    assert set(error(response)["fields"]) == {"nickname", "color"}


def test_register_trims_nickname_and_canonicalises_color(client: Client) -> None:
    data = register(client, nickname="  Sam  ", color=PLAYER_COLORS[0].lower())
    assert data["profile"]["nickname"] == "Sam"
    assert data["profile"]["color"] == PLAYER_COLORS[0]


@pytest.mark.parametrize(
    "avatar", [None, {"style": "pixel-art", "seed": "abc"}, {"style": "cutouts", "seed": "a b"}, 7]
)
def test_register_invalid_or_missing_avatar_is_replaced(client: Client, avatar: Any) -> None:
    data = register(client, avatar=avatar)
    assigned = data["profile"]["avatar"]
    assert assigned != avatar
    assert assigned["style"] in AVATAR_STYLES
    assert re.fullmatch(AVATAR_SEED_PATTERN, assigned["seed"])
    profile = Profile.objects.get()
    assert (profile.avatar_style, profile.avatar_seed) == (assigned["style"], assigned["seed"])


def test_register_imports_valid_stats(client: Client) -> None:
    stats = {"gamesPlayed": 5, "wins": 2, "byGame": {"rps": {"played": 4, "wins": 2}}}
    stats["byGame"]["hangman"] = {"played": 1, "wins": 0}
    register(client, stats=stats)
    rows = set(PlayerStats.objects.values_list("game_id", "played", "wins"))
    assert rows == {("rps", 4, 2), ("hangman", 1, 0)}


@pytest.mark.parametrize(
    "by_game",
    [
        {"rps": {"played": 1, "wins": 2}},  # wins > played
        {"rps": {"played": STATS_MAX_IMPORT_GAMES + 1, "wins": 0}},  # over the cap
        {
            "rps": {"played": STATS_MAX_IMPORT_GAMES, "wins": 0},
            "hangman": {"played": 1, "wins": 0},
        },  # total over the cap
        {"chess": {"played": 1, "wins": 0}},  # unknown game
        {"rps": {"played": 2.0, "wins": 1}},  # not an integer
        {"rps": {"played": True, "wins": True}},  # booleans are not counts
        {"rps": {"played": -1, "wins": -1}},
        {"rps": {"played": "3", "wins": 1}},
        {"rps": {"played": 3, "wins": 1}, "dots_and_boxes": "lots"},  # one bad entry voids all
        "nope",
    ],
)
def test_register_ignores_doubtful_stats(client: Client, by_game: Any) -> None:
    data = register(client, stats={"gamesPlayed": 1, "wins": 0, "byGame": by_game})
    assert not PlayerStats.objects.exists()
    assert data["profile"]["username"] == "sam_1"


def test_register_rejects_bad_json(client: Client) -> None:
    response = client.post("/api/auth/register", data="{", content_type="application/json")
    assert response.status_code == 400
    assert error(response)["code"] == "INVALID_INPUT"


def test_wrong_method_is_json_error(client: Client) -> None:
    response = client.get("/api/auth/register")
    assert response.status_code == 405
    assert error(response)["code"] == "METHOD_NOT_ALLOWED"


# Login


def test_login_good(client: Client) -> None:
    register(client, stats={"byGame": {"rps": {"played": 3, "wins": 1}}})
    response = call(client, "post", "login", {"username": "SAM_1", "password": PASSWORD})
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"token", "profile", "stats"}
    assert data["profile"]["username"] == "sam_1"
    assert data["stats"] == {
        "gamesPlayed": 3,
        "wins": 1,
        "byGame": {"rps": {"played": 3, "wins": 1}},
    }
    assert user_id_from_token(data["token"]) == User.objects.get().pk


def test_login_bad_credentials_are_generic(client: Client) -> None:
    register(client)
    wrong_password = call(client, "post", "login", {"username": "sam_1", "password": "nope-nope"})
    no_user = call(client, "post", "login", {"username": "ghost", "password": PASSWORD})
    assert wrong_password.status_code == no_user.status_code == 401
    assert wrong_password.json() == no_user.json()
    assert error(no_user)["code"] == "INVALID_CREDENTIALS"


def test_login_disabled_account_is_rejected(client: Client) -> None:
    register(client)
    User.objects.update(is_active=False)
    response = call(client, "post", "login", {"username": "sam_1", "password": PASSWORD})
    assert response.status_code == 401


def test_login_missing_fields(client: Client) -> None:
    response = call(client, "post", "login", {"username": 3})
    assert response.status_code == 400
    assert set(error(response)["fields"]) == {"username", "password"}


# Tokens and me


def test_me_returns_profile_and_stats(client: Client) -> None:
    token = register(client)["token"]
    response = call(client, "get", "me", token=token)
    assert response.status_code == 200
    assert response.json()["profile"]["nickname"] == "Sam"
    assert response.json()["stats"] == {"gamesPlayed": 0, "wins": 0, "byGame": {}}


@pytest.mark.parametrize("header", ["", "Bearer", "Bearer nonsense", "Basic abc"])
def test_me_requires_valid_token(client: Client, header: str) -> None:
    register(client)
    response = client.get("/api/auth/me", HTTP_AUTHORIZATION=header)
    assert response.status_code == 401
    assert error(response)["code"] == "UNAUTHORIZED"


def test_token_claims_and_expiry(client: Client) -> None:
    register(client)
    user = User.objects.get()
    now = datetime.now(UTC)
    claims = jwt.decode(issue_token(user.pk, now), settings.SECRET_KEY, algorithms=["HS256"])
    assert set(claims) == {"sub", "exp", "iat"}
    assert claims["sub"] == str(user.pk)
    assert claims["exp"] - claims["iat"] == AUTH_TOKEN_DAYS * 86400

    expired = issue_token(user.pk, now - timedelta(days=AUTH_TOKEN_DAYS, seconds=1))
    assert user_id_from_token(expired) is None
    assert call(client, "get", "me", token=expired).status_code == 401
    nearly = issue_token(user.pk, now - timedelta(days=AUTH_TOKEN_DAYS - 1))
    assert call(client, "get", "me", token=nearly).status_code == 200


def test_tokens_signed_otherwise_are_rejected(client: Client) -> None:
    register(client)
    user = User.objects.get()
    now = datetime.now(UTC)
    claims = {"sub": str(user.pk), "iat": now, "exp": now + timedelta(days=1)}
    forged = jwt.encode(claims, "another-secret-key-of-enough-length", algorithm="HS256")
    unsigned = jwt.encode(claims, None, algorithm="none")
    no_iat = jwt.encode({"sub": str(user.pk), "exp": claims["exp"]}, settings.SECRET_KEY)
    for token in [forged, unsigned, no_iat]:
        assert user_id_from_token(token) is None
        assert call(client, "get", "me", token=token).status_code == 401


def test_token_for_deleted_or_disabled_user_is_rejected(client: Client) -> None:
    token = register(client)["token"]
    User.objects.update(is_active=False)
    assert call(client, "get", "me", token=token).status_code == 401
    User.objects.all().delete()
    assert call(client, "get", "me", token=token).status_code == 401


# Profile edit


def test_patch_profile(client: Client) -> None:
    token = register(client)["token"]
    response = call(
        client, "patch", "profile", {"nickname": " Samwise ", "color": PLAYER_COLORS[5]}, token
    )
    assert response.status_code == 200
    assert response.json()["profile"]["nickname"] == "Samwise"
    assert response.json()["profile"]["avatar"] == AVATAR  # the avatar never changes
    profile = Profile.objects.get()
    assert (profile.nickname, profile.color) == ("Samwise", PLAYER_COLORS[5])


def test_patch_profile_partial_and_ignores_avatar(client: Client) -> None:
    token = register(client)["token"]
    body = {"color": PLAYER_COLORS[1], "avatar": {"style": "voxel-art", "seed": "zz"}}
    response = call(client, "patch", "profile", body, token)
    assert response.json()["profile"]["nickname"] == "Sam"
    assert response.json()["profile"]["color"] == PLAYER_COLORS[1]
    assert response.json()["profile"]["avatar"] == AVATAR


def test_patch_profile_invalid(client: Client) -> None:
    token = register(client)["token"]
    response = call(client, "patch", "profile", {"nickname": "<script>", "color": "red"}, token)
    assert response.status_code == 400
    assert set(error(response)["fields"]) == {"nickname", "color"}
    assert Profile.objects.get().nickname == "Sam"


def test_patch_profile_requires_token(client: Client) -> None:
    assert call(client, "patch", "profile", {"nickname": "Bob"}).status_code == 401


# Deletion


def test_delete_account_wrong_password_rejected(client: Client) -> None:
    token = register(client)["token"]
    response = call(client, "delete", "account", {"password": "wrong-password"}, token)
    assert response.status_code == 401
    assert error(response)["code"] == "INVALID_CREDENTIALS"
    assert User.objects.exists()


def test_delete_account_removes_everything(client: Client) -> None:
    token = register(client, stats={"byGame": {"rps": {"played": 2, "wins": 1}}})["token"]
    response = call(client, "delete", "account", {"password": PASSWORD}, token)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert not User.objects.exists()
    assert not Profile.objects.exists()
    assert not PlayerStats.objects.exists()
    assert call(client, "get", "me", token=token).status_code == 401


def test_delete_account_requires_token(client: Client) -> None:
    register(client)
    assert call(client, "delete", "account", {"password": PASSWORD}).status_code == 401
    assert User.objects.exists()


# Rate limits, CORS and secrets


@pytest.mark.parametrize("path", ["register", "login"])
def test_rate_limit_per_ip(client: Client, path: str) -> None:
    body = {"username": "ghost", "password": "whatever-pass"}
    for _ in range(AUTH_RATE_LIMIT_PER_MIN):
        assert call(client, "post", path, body).status_code != 429
    limited = call(client, "post", path, body)
    assert limited.status_code == 429
    assert error(limited)["code"] == "RATE_LIMITED"
    other_ip = call(client, "post", path, body, REMOTE_ADDR="10.0.0.9")
    assert other_ip.status_code != 429


def test_rate_limit_window_slides() -> None:
    now = [0.0]
    limiter = ratelimit.KeyedRateLimiter(limit=2, clock=lambda: now[0])
    assert limiter.allow("ip") and limiter.allow("ip")
    assert not limiter.allow("ip")
    now[0] = 60.0
    assert limiter.allow("ip")


def test_cors_preflight_allows_authorization(client: Client) -> None:
    response = client.options(
        "/api/auth/me",
        HTTP_ORIGIN="http://localhost:5173",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization",
    )
    assert response.status_code == 200
    assert "authorization" in response["Access-Control-Allow-Headers"]
    assert response["Access-Control-Allow-Origin"] == "http://localhost:5173"


def test_secrets_never_logged(client: Client, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    token = register(client)["token"]
    call(client, "post", "login", {"username": "sam_1", "password": PASSWORD})
    call(client, "post", "login", {"username": "sam_1", "password": "bad-password"})
    call(client, "get", "me", token=token)
    call(client, "delete", "account", {"password": PASSWORD}, token)
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert PASSWORD not in logged
    assert "bad-password" not in logged
    assert token not in logged


def test_claim_avatar_uses_assign_function(monkeypatch: pytest.MonkeyPatch) -> None:
    from rooms.avatars import SeededAvatarRng

    monkeypatch.setattr(services, "avatar_rng", SeededAvatarRng(1))
    first = services.claim_avatar(None, "Sam", PLAYER_COLORS[0])
    monkeypatch.setattr(services, "avatar_rng", SeededAvatarRng(1))
    assert services.claim_avatar({"style": "nope"}, "Sam", PLAYER_COLORS[0]) == first
