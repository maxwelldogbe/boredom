"""The Boredom admin site: Django's admin plus the dashboard pages. Staff only."""

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse

from analytics.lockout import admin_lockout
from games.constants import ADMIN_LOGIN_LOCK_MINUTES


class BoredomAdminSite(admin.AdminSite):
    site_header = "Boredom admin"
    site_title = "Boredom admin"
    index_title = "Overview"

    def get_urls(self):
        from analytics import dashboard as d

        return [*d.urls(self), *super().get_urls()]

    def index(self, request: HttpRequest, extra_context=None) -> HttpResponse:
        """The admin index is the dashboard Overview."""
        from analytics import dashboard

        return dashboard.overview(request, self)

    def login(self, request: HttpRequest, extra_context=None) -> HttpResponse:
        """Django's admin login, locked per IP + username after repeated failures."""
        if request.method != "POST":
            return super().login(request, extra_context)
        key = admin_lockout.key(
            request.META.get("REMOTE_ADDR") or "unknown", request.POST.get("username", "")
        )
        if admin_lockout.locked(key):
            context = {
                **self.each_context(request),
                "title": "Log in",
                "lockout_minutes": ADMIN_LOGIN_LOCK_MINUTES,
            }
            return TemplateResponse(request, "admin/locked_out.html", context, status=429)
        response = super().login(request, extra_context)
        if request.user.is_authenticated and request.user.is_staff:
            admin_lockout.succeeded(key)
        else:
            admin_lockout.failed(key)
        return response
