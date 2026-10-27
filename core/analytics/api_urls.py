"""Routes under /api/admin/ (staff-only JSON for the React dashboard)."""

from django.urls import path

from analytics import api

urlpatterns = [
    path("session", api.session, name="admin-api-session"),
    path("overview", api.overview, name="admin-api-overview"),
    path("games", api.games, name="admin-api-games"),
    path("games/<slug:game_id>", api.game_detail, name="admin-api-game"),
    path("users", api.users, name="admin-api-users"),
    path("users/u/<int:user_id>", api.registered_detail, name="admin-api-user"),
    path("users/g/<slug:key>", api.guest_detail, name="admin-api-guest"),
    path("users/u/<int:user_id>/<slug:action>", api.user_action, name="admin-api-user-action"),
    path("leaderboards", api.leaderboards, name="admin-api-leaderboards"),
    path("activity", api.activity, name="admin-api-activity"),
    path("reports", api.reports, name="admin-api-reports"),
    path("reports/<int:report_id>/resolve", api.resolve_report, name="admin-api-report-resolve"),
]
