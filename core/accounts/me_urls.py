"""Routes under /api/me/: the account holder's own stats, recent players and settings."""

from django.urls import path

from accounts import views
from social.views import settings_view

urlpatterns = [
    path("stats", views.my_stats, name="me-stats"),
    path("recent-players", views.recent_players, name="me-recent-players"),
    path("settings", settings_view, name="me-settings"),
]
