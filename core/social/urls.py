"""Routes under /api/: friends, blocks and reports. /api/me/settings lives in accounts.me_urls."""

from django.urls import path

from social import views

urlpatterns = [
    path("friends", views.friends, name="friends"),
    path("friends/requests", views.send_request, name="friends-request"),
    path("friends/requests/<int:request_id>/accept", views.accept_request, name="friends-accept"),
    path(
        "friends/requests/<int:request_id>/decline", views.decline_request, name="friends-decline"
    ),
    path("friends/requests/<int:request_id>", views.cancel_request, name="friends-cancel"),
    path("friends/<str:tag>/profile", views.friend_profile, name="friends-profile"),
    path("friends/<str:tag>", views.remove_friend, name="friends-remove"),
    path("blocks", views.block, name="blocks"),
    path("blocks/<str:tag>", views.unblock, name="blocks-remove"),
    path("reports", views.report, name="reports"),
]
