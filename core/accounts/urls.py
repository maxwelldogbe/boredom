"""Routes under /api/auth/."""

from django.urls import path

from accounts import views

urlpatterns = [
    path("register", views.register, name="auth-register"),
    path("login", views.login, name="auth-login"),
    path("me", views.me, name="auth-me"),
    path("profile", views.update_profile, name="auth-profile"),
    path("account", views.delete_account, name="auth-account"),
    path("password/forgot", views.forgot_password, name="auth-password-forgot"),
    path("password/reset", views.reset_password, name="auth-password-reset"),
    path("recovery/request", views.recovery_request, name="auth-recovery-request"),
]
