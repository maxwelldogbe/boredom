"""Routes under /api/brag."""

from django.urls import path

from brag import views

urlpatterns = [
    path("", views.wallet, name="brag-wallet"),
]
