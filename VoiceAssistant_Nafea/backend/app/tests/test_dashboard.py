from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

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


def test_wallet_deposit_requires_authentication() -> None:
    limiter.buckets.clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/wallet/deposit/request",
            json={
                "request_id": str(uuid4()),
                "source_account_id": str(uuid4()),
                "amount": "100.00",
            },
        )

    assert response.status_code == 401


def test_wallet_deposit_requests_first_then_uses_session_identity_and_demo_otp(
    monkeypatch,
) -> None:
    limiter.buckets.clear()
    source_account_id = uuid4()
    request_id = uuid4()
    deposit = MagicMock(
        return_value={
            "status": "completed",
            "reference": f"wallet-deposit-{request_id.hex}",
            "receipt_id": f"receipt-wallet-deposit-{request_id.hex}",
            "amount_sar": "100.00",
            "source_account_id": str(source_account_id),
            "source_bank_balance_sar": "74900.00",
            "nafi_balance_sar": "75100.00",
            "idempotent_replay": False,
        }
    )
    preview = MagicMock(
        return_value={
            "status": "awaiting_otp",
            "amount_sar": "100.00",
            "source_account_id": str(source_account_id),
            "source_bank_name": "Al Rajhi Bank",
            "source_bank_name_ar": "مصرف الراجحي",
            "source_masked_account_number": "SA00********1234",
            "source_bank_balance_sar": "75000.00",
            "nafi_balance_sar": "75000.00",
        }
    )
    monkeypatch.setattr(dashboard_store, "preview_wallet_deposit", preview)
    monkeypatch.setattr(dashboard_store, "deposit_to_wallet", deposit)

    with TestClient(app) as client:
        session = client.post(
            "/api/auth/login",
            json={"identifier": "admin", "password": "password123", "language": "en"},
        ).json()
        client.cookies.clear()
        requested = client.post(
            "/api/wallet/deposit/request",
            headers={"X-Session-Token": session["session_token"]},
            json={
                "request_id": str(request_id),
                "source_account_id": str(source_account_id),
                "amount": "100.00",
            },
        )
        confirmation_token = requested.json()["confirmation_token"]
        invalid = client.post(
            "/api/wallet/deposit/confirm",
            headers={"X-Session-Token": session["session_token"]},
            json={
                "request_id": str(request_id),
                "confirmation_token": confirmation_token,
                "otp_code": "2222",
            },
        )
        response = client.post(
            "/api/wallet/deposit/confirm",
            headers={"X-Session-Token": session["session_token"]},
            json={
                "request_id": str(request_id),
                "confirmation_token": confirmation_token,
                "otp_code": "1111",
            },
        )

    assert requested.status_code == 200
    assert requested.json()["status"] == "awaiting_otp"
    assert invalid.status_code == 403
    assert response.status_code == 200
    assert response.json()["nafi_balance_sar"] == "75100.00"
    deposit.assert_called_once_with(
        user_id="admin",
        tenant_id=settings.DEMO_TENANT_ID,
        source_account_id=str(source_account_id),
        amount=Decimal("100.00"),
        request_id=str(request_id),
    )
    preview.assert_called_once_with(
        user_id="admin",
        tenant_id=settings.DEMO_TENANT_ID,
        source_account_id=str(source_account_id),
        amount=Decimal("100.00"),
    )


def test_wallet_deposit_confirmation_rejects_a_tampered_request(monkeypatch) -> None:
    limiter.buckets.clear()
    preview = MagicMock(
        return_value={
            "status": "awaiting_otp",
            "amount_sar": "10.00",
            "source_account_id": str(uuid4()),
            "source_bank_name": "Bank",
            "source_bank_name_ar": "بنك",
            "source_masked_account_number": "SA00****1234",
            "source_bank_balance_sar": "100.00",
            "nafi_balance_sar": "50.00",
        }
    )
    deposit = MagicMock()
    monkeypatch.setattr(dashboard_store, "preview_wallet_deposit", preview)
    monkeypatch.setattr(dashboard_store, "deposit_to_wallet", deposit)

    with TestClient(app) as client:
        session = client.post(
            "/api/auth/login",
            json={"identifier": "admin", "password": "password123", "language": "en"},
        ).json()
        headers = {"X-Session-Token": session["session_token"]}
        requested = client.post(
            "/api/wallet/deposit/request",
            headers=headers,
            json={
                "request_id": str(uuid4()),
                "source_account_id": str(uuid4()),
                "amount": "10.00",
            },
        )
        response = client.post(
            "/api/wallet/deposit/confirm",
            headers=headers,
            json={
                "request_id": str(uuid4()),
                "confirmation_token": requested.json()["confirmation_token"],
                "otp_code": "1111",
            },
        )

    assert response.status_code == 403
    deposit.assert_not_called()
