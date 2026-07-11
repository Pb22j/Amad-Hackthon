"""Dependency-free HTTP wiring for the user interaction layer."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from user_interaction_layer.agentic_client.client import HttpAgenticClient, MockAgenticClient
from user_interaction_layer.application import InteractionApplication
from user_interaction_layer.config.settings import InteractionSettings
from user_interaction_layer.notifications.handler import NotificationHandler
from user_interaction_layer.orchestrator import UserInteractionOrchestrator, create_default_orchestrator
from user_interaction_layer.policy.interaction_policy import InteractionPolicy
from user_interaction_layer.security.llm_guard import OpenRouterSecurityGuard


def build_orchestrator_from_env(
    use_mock_agentic: bool | None = None,
    *,
    settings: InteractionSettings | None = None,
) -> UserInteractionOrchestrator:
    app_settings = settings or InteractionSettings.from_env()
    should_mock = app_settings.runtime.use_mock_agentic if use_mock_agentic is None else use_mock_agentic
    if should_mock or not app_settings.agentic.base_url:
        agentic_client = MockAgenticClient()
    else:
        agentic_client = HttpAgenticClient(
            base_url=app_settings.agentic.base_url,
            request_path=app_settings.agentic.request_path,
            webhook_secret=app_settings.agentic.webhook_secret or None,
        )
    return create_default_orchestrator(
        agentic_client,
        policy=_build_interaction_policy(app_settings),
    )


def build_application_from_env(
    use_mock_agentic: bool | None = None,
    *,
    settings: InteractionSettings | None = None,
) -> InteractionApplication:
    orchestrator = build_orchestrator_from_env(
        use_mock_agentic=use_mock_agentic,
        settings=settings,
    )
    return InteractionApplication(
        orchestrator=orchestrator,
        notification_handler=NotificationHandler(orchestrator.session_store),
    )


def run_dev_server(
    *,
    host: str | None = None,
    port: int | None = None,
    use_mock_agentic: bool | None = None,
) -> None:
    settings = InteractionSettings.from_env()
    application = build_application_from_env(use_mock_agentic=use_mock_agentic)
    server_host = host or settings.runtime.host
    server_port = port or settings.runtime.port
    handler = _make_handler(application)
    server = ThreadingHTTPServer((server_host, server_port), handler)
    print(f"User interaction server listening on http://{server_host}:{server_port}")
    server.serve_forever()


def _make_handler(application: InteractionApplication) -> type[BaseHTTPRequestHandler]:
    class InteractionRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                self._write_json({"status": "ok"})
                return
            self._write_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            try:
                payload = self._read_json()
                if self.path == "/interaction/chat":
                    response = application.handle_chat(payload)
                elif self.path == "/interaction/voice/transcript":
                    response = application.handle_voice_transcript(payload)
                elif self.path == "/interaction/agentic-notification":
                    response = application.handle_agentic_notification(payload)
                else:
                    self._write_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
                    return
            except ValueError as exc:
                self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception:
                self._write_json(
                    {"error": "internal_error"},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return

            self._write_json(response)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8") or "{}")
            except json.JSONDecodeError as exc:
                raise ValueError("Request body must be valid JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object")
            return payload

        def _write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return InteractionRequestHandler


def _build_interaction_policy(settings: InteractionSettings) -> InteractionPolicy:
    guard = None
    if settings.security.guard_provider == "openrouter":
        if settings.openrouter.api_key and settings.security.guard_model:
            guard = OpenRouterSecurityGuard(
                api_key=settings.openrouter.api_key,
                model=settings.security.guard_model,
                base_url=settings.openrouter.base_url,
                timeout_seconds=settings.security.guard_timeout_seconds,
            )
    elif settings.security.guard_provider in {"none", "deterministic"}:
        guard = None
    else:
        raise ValueError(f"Unsupported SECURITY_GUARD_PROVIDER: {settings.security.guard_provider}")

    return InteractionPolicy(
        security_guard=guard,
        require_security_guard=settings.security.guard_required,
    )
