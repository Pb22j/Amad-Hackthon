import hashlib
import hmac

import httpx
import pytest

from agentic.telemetry.events import WebhookEventPublisher


@pytest.mark.integration
async def test_webhook_events_are_signed(agentic_request):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        captured["timestamp"] = request.headers["x-agentic-timestamp"]
        captured["signature"] = request.headers["x-agentic-signature"]
        return httpx.Response(204)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    from agentic.api.schemas import AgentEvent, AgentEventType

    event = AgentEvent(
        task_id=agentic_request.request_id,
        request_id=agentic_request.request_id,
        session_id=agentic_request.session_id,
        event_type=AgentEventType.COMPLETED,
        user_safe_summary="Done",
    )
    publisher = WebhookEventPublisher(
        "https://interaction.test/events", "w" * 32, client=client
    )
    await publisher.publish(event)
    expected = hmac.new(
        b"w" * 32,
        captured["timestamp"].encode() + b"." + captured["body"],
        hashlib.sha256,
    ).hexdigest()
    assert hmac.compare_digest(expected, captured["signature"])
    await client.aclose()


@pytest.mark.integration
async def test_webhook_retries_and_reports_delivery_failure(agentic_request):
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    from agentic.api.schemas import AgentEvent, AgentEventType

    event = AgentEvent(
        task_id=agentic_request.request_id,
        request_id=agentic_request.request_id,
        session_id=agentic_request.session_id,
        event_type=AgentEventType.FAILED,
        user_safe_summary="Failed",
    )
    publisher = WebhookEventPublisher(
        "https://interaction.test/events", "w" * 32, client=client, attempts=2
    )
    with pytest.raises(RuntimeError, match="failed to deliver"):
        await publisher.publish(event)
    assert attempts == 2
    await publisher.close()
    await client.aclose()
