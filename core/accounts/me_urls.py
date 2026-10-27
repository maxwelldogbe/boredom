"""Routes under /api/me/: the account holder's own stats and recent players."""

from django.urls import path

from accounts import views

urlpatterns = [
    path("stats", views.my_stats, name="me-stats"),
    path("recent-players", views.recent_players, name="me-recent-players"),
]
