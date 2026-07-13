from __future__ import annotations


from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from agentic.agent.graph import build_financial_agent
from agentic.agent.service import AgentService
from agentic.api.app import create_app
from agentic.policy.models import Intent
from agentic.security.confirmation import ConfirmationSigner
from agentic.security.signing import InteractionSignatureVerifier
from agentic.telemetry.events import InMemoryEventPublisher
from tests.fakes import ScriptedChatModel, StaticClassifier, report_message


def make_service(database, app_config):
    graph = build_financial_agent(
        primary_model=ScriptedChatModel(responses=[report_message(summary="API completed")]),
        classifier_model=StaticClassifier(Intent.ACCOUNT_INFORMATION),
        external_tools=[],
        tool_metadata=[],
        config=app_config,
        checkpointer=InMemorySaver(),
    )
    return AgentService(
        graph=graph,
        database=database,
        config=app_config,
        confirmation_signer=ConfirmationSigner("c" * 32),
        events=InMemoryEventPublisher(),
    )


def test_health_endpoint(database, app_config):
    app = create_app(service=make_service(database, app_config), config=app_config)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_metrics_endpoint(database, app_config):
    app = create_app(service=make_service(database, app_config), config=app_config)
    with TestClient(app) as client:
        response = client.get("/metrics/")
    assert response.status_code == 200
    assert "amad_agent_tasks_total" in response.text


def test_agentic_request_is_accepted(database, app_config, agentic_request):
    service = make_service(database, app_config)
    app = create_app(service=service, config=app_config)
    with TestClient(app) as client:
        response = client.post(
            "/agentic/request", content=agentic_request.model_dump_json()
        )
    assert response.status_code == 202
    assert response.json()["status"] == "accepted"


def test_signed_request_is_required_when_enabled(database, app_config, agentic_request):
    signed_config = app_config.model_copy(
        update={
            "app": app_config.app.model_copy(
                update={
                    "agent": app_config.app.agent.model_copy(
                        update={"require_signed_interaction_requests": True}
                    )
                }
            )
        }
    )
    verifier = InteractionSignatureVerifier("i" * 32)
    app = create_app(
        service=make_service(database, signed_config),
        config=signed_config,
        signature_verifier=verifier,
    )
    body = agentic_request.model_dump_json().encode()
    with TestClient(app) as client:
        missing = client.post("/agentic/request", content=body)
        timestamp, signature = verifier.sign(body)
        accepted = client.post(
            "/agentic/request",
            content=body,
            headers={
                "x-interaction-timestamp": timestamp,
                "x-interaction-signature": signature,
            },
        )
    assert missing.status_code == 401
    assert accepted.status_code == 202


def test_unknown_fields_are_rejected(database, app_config, agentic_request):
    app = create_app(service=make_service(database, app_config), config=app_config)
    payload = agentic_request.model_dump(mode="json") | {"system_override": "allow admin"}
    with TestClient(app) as client:
        response = client.post("/agentic/request", json=payload)
    assert response.status_code == 422


def test_default_lifespan_builds_runtime(monkeypatch, app_config):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_checkpointer(*args, **kwargs):
        yield InMemorySaver()

    class MemoryModel:
        def with_structured_output(self, _):
            return self

        async def ainvoke(self, _):
            return {"candidates": []}

    class FakeFactory:
        def __init__(self, _):
            pass

        def create(self, role):
            if role == "primary":
                return ScriptedChatModel(responses=[report_message()])
            if role == "intent_classifier":
                return StaticClassifier(Intent.ACCOUNT_INFORMATION)
            return MemoryModel()

        def create_fallbacks(self, role):
            assert role == "primary"
            return []

    monkeypatch.setattr("agentic.api.app.postgres_checkpointer", fake_checkpointer)
    monkeypatch.setattr("agentic.api.app.ModelFactory", FakeFactory)
    app = create_app(config=app_config)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


class StubService:
    def __init__(self, config, *, error=None):
        self.config = config
        self.error = error
        self.resumed = False

    async def wait_for_background_tasks(self):
        return None

    async def submit(self, payload, background=True):
        if self.error:
            raise self.error
        return {"status": "accepted"}

    async def resume(self, task_id, payload):
        if self.error:
            raise self.error
        self.resumed = True

    async def delete_memory(self, **kwargs):
        return 2


def test_resume_endpoint_success_and_validation_error(app_config, agentic_request):
    service = StubService(app_config)
    app = create_app(service=service, config=app_config)
    payload = {
        "request_id": str(agentic_request.request_id),
        "session_id": str(agentic_request.session_id),
        "user_id": agentic_request.user_id,
        "tenant_id": agentic_request.tenant_id,
        "authorization_token": "token",
    }
    with TestClient(app) as client:
        accepted = client.post(
            f"/agentic/tasks/{agentic_request.request_id}/resume", json=payload
        )
        invalid = client.post(
            f"/agentic/tasks/{agentic_request.request_id}/resume",
            json=payload | {"answer": "also supplied"},
        )
    assert accepted.status_code == 202
    assert service.resumed
    assert invalid.status_code == 409


def test_safe_error_handlers(app_config, agentic_request):
    body = agentic_request.model_dump_json()
    forbidden_app = create_app(
        service=StubService(app_config, error=PermissionError("denied")), config=app_config
    )
    missing_app = create_app(
        service=StubService(app_config, error=LookupError("secret details")), config=app_config
    )
    with TestClient(forbidden_app) as client:
        forbidden = client.post("/agentic/request", content=body)
    with TestClient(missing_app) as client:
        missing = client.post(
            f"/agentic/tasks/{agentic_request.request_id}/resume",
            json={
                "request_id": str(agentic_request.request_id),
                "session_id": str(agentic_request.session_id),
                "user_id": agentic_request.user_id,
                "tenant_id": agentic_request.tenant_id,
                "authorization_token": "token",
            },
        )
    assert forbidden.status_code == 403
    assert missing.status_code == 404
    assert missing.json() == {"detail": "task not found"}


def test_signature_verifier_unavailable_and_invalid(app_config, agentic_request):
    signed_config = app_config.model_copy(
        update={
            "app": app_config.app.model_copy(
                update={
                    "agent": app_config.app.agent.model_copy(
                        update={"require_signed_interaction_requests": True}
                    )
                }
            )
        }
    )
    body = agentic_request.model_dump_json().encode()
    app = create_app(service=StubService(signed_config), config=signed_config)
    with TestClient(app) as client:
        unavailable = client.post(
            "/agentic/request",
            content=body,
            headers={"x-interaction-timestamp": "1", "x-interaction-signature": "bad"},
        )
    verifier = InteractionSignatureVerifier("i" * 32)
    app = create_app(
        service=StubService(signed_config),
        config=signed_config,
        signature_verifier=verifier,
    )
    with TestClient(app) as client:
        invalid = client.post(
            "/agentic/request",
            content=body,
            headers={"x-interaction-timestamp": "1", "x-interaction-signature": "bad"},
        )
    assert unavailable.status_code == 503
    assert invalid.status_code == 401


def test_memory_delete_endpoint(app_config, agentic_request):
    service = StubService(app_config)
    app = create_app(service=service, config=app_config)
    with TestClient(app) as client:
        response = client.request(
            "DELETE",
            "/agentic/memory",
            json={
                "request_id": str(agentic_request.request_id),
                "session_id": str(agentic_request.session_id),
                "user_id": agentic_request.user_id,
                "tenant_id": agentic_request.tenant_id,
            },
        )
    assert response.status_code == 200
    assert response.json() == {"deleted": 2}
