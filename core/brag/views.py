"""GET /api/brag: the signed-in player's Brag coins."""

from typing import Any

from django.contrib.auth.models import User
from django.http import HttpRequest, JsonResponse

from accounts.views import api
from brag.services import summary


@api("GET", auth=True, no_store=True)
def wallet(request: HttpRequest, body: dict[str, Any], user: User | None) -> JsonResponse:
    assert user is not None
    return JsonResponse(summary(user))
