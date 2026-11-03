"""Solo records in the Django admin: a read-only list."""

from django.contrib import admin
from django.http import HttpRequest

from solo.models import SoloRecord


@admin.register(SoloRecord)
class SoloRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "game_id", "variant", "plays", "wins", "losses", "draws", "updated_at")
    list_filter = ("game_id", "variant")
    readonly_fields = [f.name for f in SoloRecord._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False
