"""Reports in the Django admin (read-only lists; resolving is done from the dashboard).

Registering the model gives resolve and dismiss their LogEntry audit rows.
"""

from django.contrib import admin
from django.http import HttpRequest

from social.models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "status", "reason", "reported_nickname")
    list_filter = ("status", "reason")
    readonly_fields = [f.name for f in Report._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
