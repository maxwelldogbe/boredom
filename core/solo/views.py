"""GET /api/solo/records: the signed-in player's solo records."""

from typing import Any

from django.contrib.auth.models import User
from django.http import HttpRequest, JsonResponse

from accounts.views import api
from solo.services import records_for


@api("GET", auth=True, no_store=True)
def records(request: HttpRequest, body: dict[str, Any], user: User | None) -> JsonResponse:
    assert user is not None
    return JsonResponse(records_for(user), safe=False)
