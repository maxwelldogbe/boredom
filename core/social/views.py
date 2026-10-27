"""Friends, blocks, reports and the presence setting over HTTP (Bearer token, no-store).

Every error is {"error": {"code", "message", "fields"?}}, as in the accounts API.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any

from django.contrib.auth.models import User
from django.http import HttpRequest, JsonResponse

from accounts.models import Profile
from accounts.views import ApiError, api, by_method, invalid
from social import notify, services
from social.services import SocialError

STATUS = {
    "INVALID_INPUT": 400,
    "SELF": 400,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "ALREADY_FRIENDS": 409,
    "ALREADY_REQUESTED": 409,
    "LIMIT_REACHED": 409,
    "RATE_LIMITED": 429,
}
OK = {"ok": True}


def social_api(method: str) -> Callable[..., Callable[..., JsonResponse]]:
    """`api(method, auth=True, no_store=True)`, rendering SocialError in the same format."""

    def decorate(view: Callable[..., JsonResponse]) -> Callable[..., JsonResponse]:
        @wraps(view)
        def inner(request: HttpRequest, body: dict[str, Any], user: User | None, **kw: Any):
            assert user is not None
            try:
                return view(request, body, user, **kw)
            except SocialError as exc:
                raise ApiError(STATUS[exc.code], exc.code, exc.message, exc.fields) from None

        return api(method, auth=True, no_store=True)(inner)

    return decorate


# ----- friends -------------------------------------------------------------------------------


@social_api("GET")
def friends(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    return JsonResponse(services.overview(user))


@social_api("POST")
def send_request(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    target = services.profile_by_tag(body.get("tag"))
    return JsonResponse(services.send_request(user, target))


@social_api("POST")
def accept_request(
    request: HttpRequest, body: dict[str, Any], user: User, request_id: int
) -> JsonResponse:
    services.accept_request(user, request_id)
    return JsonResponse({"status": "friends"})


@social_api("POST")
def decline_request(
    request: HttpRequest, body: dict[str, Any], user: User, request_id: int
) -> JsonResponse:
    services.decline_request(user, request_id)
    return JsonResponse(OK)


@social_api("DELETE")
def cancel_request(
    request: HttpRequest, body: dict[str, Any], user: User, request_id: int
) -> JsonResponse:
    services.cancel_request(user, request_id)
    return JsonResponse(OK)


@social_api("DELETE")
def remove_friend(request: HttpRequest, body: dict[str, Any], user: User, tag: str) -> JsonResponse:
    services.remove_friend(user, services.profile_by_tag(tag))
    return JsonResponse(OK)


@social_api("GET")
def friend_profile(
    request: HttpRequest, body: dict[str, Any], user: User, tag: str
) -> JsonResponse:
    try:
        target = services.profile_by_tag(tag)
    except SocialError:
        raise SocialError("FORBIDDEN", "Only friends can see this profile.") from None
    return JsonResponse(services.friend_profile(user, target))


# ----- blocks and reports --------------------------------------------------------------------


@social_api("POST")
def block(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    services.block(user, services.profile_by_tag(body.get("tag")))
    return JsonResponse(OK)


@social_api("DELETE")
def unblock(request: HttpRequest, body: dict[str, Any], user: User, tag: str) -> JsonResponse:
    services.unblock(user, services.profile_by_tag(tag))
    return JsonResponse(OK)


@social_api("POST")
def report(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    target = services.profile_by_tag(body.get("tag"))
    services.report(user, body.get("reason"), body.get("note"), target=target)
    return JsonResponse(OK)


# ----- settings ------------------------------------------------------------------------------


def _settings(profile: Profile) -> dict[str, Any]:
    return {"presence": profile.presence_mode}


@social_api("GET")
def get_settings(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    return JsonResponse(_settings(user.profile))


@social_api("PATCH")
def update_settings(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    profile = user.profile
    if "presence" in body:
        if body["presence"] not in Profile.PresenceMode.values:
            raise invalid({"presence": "Choose online, busy or offline."})
        profile.presence_mode = body["presence"]
        profile.save(update_fields=["presence_mode"])
        notify.mode_changed(user.pk, profile.presence_mode)
    return JsonResponse(_settings(profile))


settings_view = by_method(get=get_settings, patch=update_settings)
