"""Account HTTP API: plain JSON views. Tokens travel in the Authorization header, so CSRF
does not apply. Every error is {"error": {"code", "message", "fields"?}}.
"""

import json
import re
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from accounts import me as me_data
from accounts import services
from accounts.ratelimit import KeyedRateLimiter, login_limiter, register_limiter
from accounts.tags import ensure_tag
from accounts.tokens import issue_token, user_id_from_token
from games.constants import AVATAR_CHANGE_DAYS, USERNAME_PATTERN
from rooms.avatars import validate_avatar
from rooms.models_types import RoomError
from rooms.validation import validate_color, validate_nickname

USERNAME_RE = re.compile(USERNAME_PATTERN)
PASSWORD_MAX = 128
BAD_CREDENTIALS = "Wrong username or password."

View = Callable[[HttpRequest, dict[str, Any], User | None], JsonResponse]


class ApiError(Exception):
    def __init__(
        self, status: int, code: str, message: str, fields: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.fields = status, code, message, fields

    def response(self) -> JsonResponse:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.fields:
            error["fields"] = self.fields
        return JsonResponse({"error": error}, status=self.status)


def invalid(fields: dict[str, str]) -> ApiError:
    return ApiError(400, "INVALID_INPUT", "Some fields need fixing.", fields)


def _json_body(request: HttpRequest) -> dict[str, Any]:
    if not request.body:
        return {}
    try:
        body = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise ApiError(400, "INVALID_INPUT", "Request body is not valid JSON.") from None
    if not isinstance(body, dict):
        raise ApiError(400, "INVALID_INPUT", "Request body must be a JSON object.")
    return body


def _bearer_user(request: HttpRequest) -> User:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    user_id = user_id_from_token(token.strip()) if scheme.lower() == "bearer" else None
    user = (
        User.objects.select_related("profile").filter(pk=user_id, is_active=True).first()
        if user_id is not None
        else None
    )
    if user is None or not hasattr(user, "profile"):
        raise ApiError(401, "UNAUTHORIZED", "Please log in again.")
    return user


def _client_ip(request: HttpRequest) -> str:
    return request.META.get("REMOTE_ADDR") or "unknown"


def api(
    method: str,
    *,
    auth: bool = False,
    limiter: KeyedRateLimiter | None = None,
    no_store: bool = False,
) -> Callable[[View], Callable[[HttpRequest], JsonResponse]]:
    """Method check, rate limit, JSON body, bearer auth and error rendering for one view.

    `no_store` marks every response, errors included, Cache-Control: no-store.
    """

    def decorate(view: View) -> Callable[[HttpRequest], JsonResponse]:
        @csrf_exempt
        @wraps(view)
        def wrapper(request: HttpRequest) -> JsonResponse:
            try:
                if request.method != method:
                    raise ApiError(405, "METHOD_NOT_ALLOWED", f"Use {method}.")
                if limiter is not None and not limiter.allow(_client_ip(request)):
                    raise ApiError(429, "RATE_LIMITED", "Too many attempts. Wait a minute.")
                body = _json_body(request)
                user = _bearer_user(request) if auth else None
                response = view(request, body, user)
            except ApiError as exc:
                response = exc.response()
            if no_store:
                response["Cache-Control"] = "no-store"
            return response

        return wrapper

    return decorate


def _field(fields: dict[str, str], name: str, check: Callable[[Any], Any], raw: Any) -> Any:
    """Run a room validator, recording its message under `name` on failure."""
    try:
        return check(raw)
    except RoomError as exc:
        fields[name] = exc.message
        return None


def _session(user: User) -> dict[str, Any]:
    return {"token": issue_token(user.pk), "profile": services.public_profile(user.profile)}


@api("POST", limiter=register_limiter)
def register(request: HttpRequest, body: dict[str, Any], user: User | None) -> JsonResponse:
    fields: dict[str, str] = {}
    username, password = body.get("username"), body.get("password")
    if not isinstance(username, str) or not USERNAME_RE.fullmatch(username):
        fields["username"] = "Use 3 to 20 letters, numbers or underscores."
    if not isinstance(password, str) or len(password) > PASSWORD_MAX:
        fields["password"] = "Choose a password."
    elif "username" not in fields:
        try:
            validate_password(password, User(username=username))
        except ValidationError as exc:
            fields["password"] = " ".join(exc.messages)
    profile = body.get("profile")
    if not isinstance(profile, dict):
        profile = {}
    nickname = _field(fields, "nickname", validate_nickname, profile.get("nickname"))
    color = _field(fields, "color", validate_color, profile.get("color"))
    if fields:
        raise invalid(fields)
    taken = ApiError(409, "USERNAME_TAKEN", "That username is taken.", {"username": "Taken."})
    if User.objects.filter(username__iexact=username).exists():
        raise taken
    avatar = services.claim_avatar(profile.get("avatar"), nickname, color)
    stats = services.clean_imported_stats(profile.get("stats"))
    try:
        account = services.create_account(username, password, nickname, color, avatar, stats)
    except IntegrityError:
        raise taken from None
    return JsonResponse(_session(account), status=201)


@api("POST", limiter=login_limiter)
def login(request: HttpRequest, body: dict[str, Any], user: User | None) -> JsonResponse:
    username, password = body.get("username"), body.get("password")
    fields = {}
    if not isinstance(username, str) or not username:
        fields["username"] = "Enter your username."
    if not isinstance(password, str) or not password:
        fields["password"] = "Enter your password."
    if fields:
        raise invalid(fields)
    account = None
    if len(username) <= 150 and len(password) <= PASSWORD_MAX:
        # Usernames are unique ignoring case (see register), so log in ignoring case too.
        stored = User.objects.filter(username__iexact=username).values_list("username", flat=True)
        username = stored.first() or username
        account = authenticate(request, username=username, password=password)
    if account is None or not hasattr(account, "profile"):
        services.recorder.record_event("login_failed")  # the username is never stored
        raise ApiError(401, "INVALID_CREDENTIALS", BAD_CREDENTIALS)
    services.recorder.record_event("login", user_id=account.pk)
    return JsonResponse({**_session(account), "stats": services.public_stats(account)})


@api("GET", auth=True, no_store=True)
def me(request: HttpRequest, body: dict[str, Any], user: User | None) -> JsonResponse:
    """The owner's profile and stats, plus the public tag and an ISO-8601 createdAt."""
    assert user is not None
    profile = user.profile
    return JsonResponse(
        {
            "profile": services.public_profile(profile),
            "stats": services.public_stats(user),
            "tag": ensure_tag(profile),
            "createdAt": me_data.iso(profile.created_at),
        }
    )


@api("GET", auth=True, no_store=True)
def my_stats(request: HttpRequest, body: dict[str, Any], user: User | None) -> JsonResponse:
    assert user is not None
    return JsonResponse(me_data.stats(user))


@api("GET", auth=True, no_store=True)
def recent_players(request: HttpRequest, body: dict[str, Any], user: User | None) -> JsonResponse:
    assert user is not None
    return JsonResponse({"players": me_data.recent_players(user)})


@api("PATCH", auth=True)
def update_profile(request: HttpRequest, body: dict[str, Any], user: User | None) -> JsonResponse:
    assert user is not None
    profile, fields = user.profile, {}
    if "nickname" in body:
        profile.nickname = _field(fields, "nickname", validate_nickname, body["nickname"])
    if "color" in body:
        profile.color = _field(fields, "color", validate_color, body["color"])
    avatar = _field(fields, "avatar", validate_avatar, body["avatar"]) if "avatar" in body else None
    if fields:
        raise invalid(fields)
    update = ["nickname", "color"]
    now = timezone.now()
    current = (profile.avatar_style, profile.avatar_seed)
    if avatar is not None and (avatar.style, avatar.seed) != current:
        # Checked before anything is saved, so a locked avatar keeps the whole request unsaved.
        if services.avatar_locked_until(profile, now):
            raise ApiError(
                409,
                "AVATAR_LOCKED",
                f"You can change your avatar once every {AVATAR_CHANGE_DAYS} days.",
                {"avatar": f"You can change your avatar once every {AVATAR_CHANGE_DAYS} days."},
            )
        profile.avatar_style, profile.avatar_seed = avatar.style, avatar.seed
        profile.avatar_changed_at = now
        update += ["avatar_style", "avatar_seed", "avatar_changed_at"]
    profile.save(update_fields=update)
    return JsonResponse({"profile": services.public_profile(profile)})


@api("DELETE", auth=True)
def delete_account(request: HttpRequest, body: dict[str, Any], user: User | None) -> JsonResponse:
    assert user is not None
    password = body.get("password")
    if not isinstance(password, str) or not password:
        raise invalid({"password": "Enter your password."})
    if len(password) > PASSWORD_MAX or not user.check_password(password):
        raise ApiError(401, "INVALID_CREDENTIALS", "Wrong password.")
    services.delete_account(user)
    return JsonResponse({"ok": True})
