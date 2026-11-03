"""Routes under /api/solo/."""

from django.urls import path

from solo import views

urlpatterns = [
    path("records", views.records, name="solo-records"),
]
