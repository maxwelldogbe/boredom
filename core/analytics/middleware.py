"""Keep the admin out of search engines."""

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse


class AdminNoIndexMiddleware:
    """Add `X-Robots-Tag: noindex, nofollow` to every response under ADMIN_URL_PREFIX."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.prefix = "/" + settings.ADMIN_URL_PREFIX

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if request.path.startswith(self.prefix):
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response
