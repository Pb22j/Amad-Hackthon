"""Clients for submitting natural-language requests to the agentic layer."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from user_interaction_layer.agentic_client.schemas import (
    AgenticRequest,
    AgenticResponse,
    AgenticStatus,
)


class AgenticClientError(RuntimeError):
    """Raised when the agentic layer cannot accept a request."""


class AgenticClient(Protocol):
    def submit_request(self, request: AgenticRequest) -> AgenticResponse:
        """Submit one natural-language request to the agentic layer."""


@dataclass
class HttpAgenticClient:
    base_url: str
    request_path: str = "/agentic/request"
    timeout_seconds: float = 20.0
    webhook_secret: str | None = None

    def submit_request(self, request: AgenticRequest) -> AgenticResponse:
        url = f"{self.base_url.rstrip('/')}{self.request_path}"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.webhook_secret:
            headers["X-Agentic-Webhook-Secret"] = self.webhook_secret

        body = json.dumps(request.to_payload()).encode("utf-8")
        http_request = urllib.request.Request(url, data=body, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise AgenticClientError(f"Agentic request failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AgenticClientError("Agentic request failed because the service is unavailable") from exc
        except json.JSONDecodeError as exc:
            raise AgenticClientError("Agentic response was not valid JSON") from exc

        return AgenticResponse.from_payload(payload)


@dataclass
class MockAgenticClient:
    accepted_message: str = ""
    submitted_requests: list[AgenticRequest] = field(default_factory=list)

    def submit_request(self, request: AgenticRequest) -> AgenticResponse:
        self.submitted_requests.append(request)
        return AgenticResponse(
            request_id=request.request_id,
            task_id=str(uuid4()),
            status=AgenticStatus.ACCEPTED,
            user_safe_message=self.accepted_message,
        )

