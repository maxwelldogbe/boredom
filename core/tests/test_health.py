"""HTTP health endpoint."""

from django.test import Client


def test_health_returns_ok() -> None:
    response = Client().get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_health_rejects_post() -> None:
    assert Client().post("/api/health").status_code == 405
