"""Activity models in the admin: read-only for staff; deletion for superusers only."""

from django.contrib import admin
from django.http import HttpRequest

from analytics.models import ActivityEvent, GameParticipation, GameSession


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        return request.user.is_active and request.user.is_staff

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_active and request.user.is_staff

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return request.user.is_active and request.user.is_superuser


class ParticipationInline(admin.TabularInline):
    model = GameParticipation
    extra = 0
    can_delete = False
    fields = (
        "nickname",
        "player_type",
        "placement",
        "raw_score",
        "session_points",
        "is_win",
        "left_early",
    )
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


@admin.register(GameSession)
class GameSessionAdmin(ReadOnlyAdmin):
    list_display = (
        "game_id",
        "status",
        "started_at",
        "duration_seconds",
        "player_count",
        "room_code",
    )
    list_filter = ("status", "game_id")
    date_hierarchy = "started_at"
    ordering = ("-started_at",)
    inlines = [ParticipationInline]


@admin.register(GameParticipation)
class GameParticipationAdmin(ReadOnlyAdmin):
    list_display = ("nickname", "player_type", "session", "placement", "is_win", "left_early")
    list_filter = ("player_type", "is_win", "left_early", "session__game_id")
    list_select_related = ("session",)
    search_fields = ("nickname",)
    ordering = ("-session__started_at",)


@admin.register(ActivityEvent)
class ActivityEventAdmin(ReadOnlyAdmin):
    list_display = ("kind", "occurred_at", "user", "guest_key", "room_code", "game_id")
    list_filter = ("kind", "game_id")
    date_hierarchy = "occurred_at"
    ordering = ("-occurred_at",)
    list_select_related = ("user",)
