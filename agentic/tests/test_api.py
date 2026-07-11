from __future__ import annotations

from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from agentic_service.api import create_app


class RecordingService:
    def __init__(self) -> None:
        self.submitted: list[dict] = []
        self.tasks: dict[str, dict] = {
            "task-1": {
                "task_id": "task-1",
                "request_id": "request-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "state": "accepted",
            }
        }

    def submit(self, payload: dict) -> dict:
        self.submitted.append(payload)
        return {
            "request_id": payload["request_id"],
            "task_id": "task-1",
            "status": "accepted",
            "user_safe_message": "Request accepted.",
        }

    def get_task(self, task_id: str, user_id: str | None = None) -> dict | None:
        task = self.tasks.get(task_id)
        if task is None or (user_id is not None and task["user_id"] != user_id):
            return None
        return task

    def capabilities(self) -> dict:
        return {"mode": "mock", "capabilities": {"own_account_transfer": True}}


class SecretRecordingService(RecordingService):
    def __init__(self) -> None:
        super().__init__()
        self.settings = SimpleNamespace(request_webhook_secret="request-secret")


def valid_payload() -> dict:
    return {
        "request_id": "request-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "channel": "chat",
        "language": "en",
        "natural_language_request": "Transfer 25 SAR to my savings account.",
        "original_user_message": "Transfer 25 SAR to my savings account.",
        "confirmation": {"required": False, "received": True},
        "metadata": {
            "created_at": "2026-07-10T00:00:00+00:00",
            "source_provider": "openrouter",
            "conversation_context_summary": "",
        },
    }


class AgenticApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RecordingService()
        self.client = TestClient(create_app(self.service))

    def test_health_endpoints_are_available(self) -> None:
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/health/live").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/health/ready").json(), {"status": "ready"})

    def test_request_preserves_interaction_wire_contract(self) -> None:
        response = self.client.post("/agentic/request", json=valid_payload())

        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            response.json(),
            {
                "request_id": "request-1",
                "task_id": "task-1",
                "status": "accepted",
                "user_safe_message": "Request accepted.",
            },
        )
        self.assertEqual(self.service.submitted[0]["natural_language_request"], valid_payload()["natural_language_request"])
        self.assertNotIn("normalized_intent", self.service.submitted[0])

    def test_request_rejects_an_invalid_wire_payload(self) -> None:
        payload = valid_payload()
        del payload["metadata"]

        response = self.client.post("/agentic/request", json=payload)

        self.assertEqual(response.status_code, 422)

    def test_capabilities_are_delegated_to_the_service(self) -> None:
        response = self.client.get("/agentic/capabilities")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "mock")
        self.assertTrue(response.json()["capabilities"]["own_account_transfer"])

    def test_task_lookup_is_user_scoped(self) -> None:
        response = self.client.get("/agentic/tasks/task-1?user_id=user-1")
        missing = self.client.get("/agentic/tasks/task-1?user_id=another-user")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "accepted")
        self.assertEqual(missing.status_code, 404)

    def test_task_lookup_requires_a_user_scope(self) -> None:
        self.assertEqual(self.client.get("/agentic/tasks/task-1").status_code, 422)

    def test_request_secret_is_checked_when_the_service_configures_one(self) -> None:
        client = TestClient(create_app(SecretRecordingService()))
        denied = client.post("/agentic/request", json=valid_payload())
        allowed = client.post(
            "/agentic/request", json=valid_payload(), headers={"X-Agentic-Webhook-Secret": "request-secret"}
        )

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(allowed.status_code, 202)

        denied_read = client.get("/agentic/tasks/task-1?user_id=user-1")
        allowed_read = client.get(
            "/agentic/tasks/task-1?user_id=user-1",
            headers={"X-Agentic-Webhook-Secret": "request-secret"},
        )
        self.assertEqual(denied_read.status_code, 401)
        self.assertEqual(allowed_read.status_code, 200)


if __name__ == "__main__":
    unittest.main()
