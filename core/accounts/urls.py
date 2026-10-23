"""Routes under /api/auth/."""

from django.urls import path

from accounts import views

urlpatterns = [
    path("register", views.register, name="auth-register"),
    path("login", views.login, name="auth-login"),
    path("me", views.me, name="auth-me"),
    path("profile", views.update_profile, name="auth-profile"),
    path("account", views.delete_account, name="auth-account"),
]
