from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app, dashboard_store, limiter


def test_dashboard_requires_an_authenticated_interaction_session() -> None:
    limiter.buckets.clear()
    with TestClient(app) as client:
        response = client.get("/api/dashboard")

    assert response.status_code == 401


def test_dashboard_uses_only_the_server_owned_session_identity(monkeypatch) -> None:
    limiter.buckets.clear()
    snapshot = {
        "as_of": "2026-07-15T12:00:00+00:00",
        "user": {"name": "Demo", "name_ar": "تجريبي", "initial": "D"},
    }
    read_snapshot = MagicMock(return_value=snapshot)
    monkeypatch.setattr(dashboard_store, "snapshot", read_snapshot)

    with TestClient(app) as client:
        session = client.post(
            "/api/auth/login",
            json={"identifier": "admin", "password": "password123", "language": "en"},
        ).json()
        client.cookies.clear()
        response = client.get(
            "/api/dashboard",
            headers={"X-Session-Token": session["session_token"]},
        )

    assert response.status_code == 200
    assert response.json() == snapshot
    read_snapshot.assert_called_once_with(
        user_id="admin",
        tenant_id=settings.DEMO_TENANT_ID,
    )
