"""HTTP routes. The game itself runs over the WebSocket at /ws/ (see config/asgi.py)."""

from django.contrib import admin
from django.http import HttpRequest, JsonResponse
from django.urls import path
from django.views.decorators.http import require_GET


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """Liveness check used by hosting platforms and the client's wake-up screen."""
    return JsonResponse({"ok": True})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health", health, name="health"),
]
