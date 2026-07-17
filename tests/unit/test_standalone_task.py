from __future__ import annotations

import base64
import inspect
import json

import pytest

from evaluation import task


@pytest.fixture(autouse=True)
def evaluation_environment(monkeypatch) -> None:
    monkeypatch.setenv("INTERACTION_SHARED_SECRET", "i" * 32)
    monkeypatch.setenv("CONFIRMATION_SIGNING_KEY", "c" * 32)
    monkeypatch.setenv("AGENTIC_EVALUATION_TIMEOUT_SECONDS", "5")


def test_run_agent_uses_only_query_and_returns_api_report(monkeypatch) -> None:
    responses = iter(
        [
            {"task_id": "task-1", "status": "accepted"},
            {"task_id": "task-1", "status": "running"},
            {
                "task_id": "task-1",
                "status": "completed",
                "final_report": {"status": "completed", "summary": "Balance retrieved."},
            },
        ]
    )
    monkeypatch.setattr(task, "_post_json", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(task.time, "sleep", lambda _: None)

    assert list(inspect.signature(task.run_agent).parameters) == ["query"]
    assert task.run_agent("  Show my balance.  ") == {
        "status": "completed",
        "summary": "Balance retrieved.",
    }


def test_run_agent_returns_clarification_without_inventing_data(monkeypatch) -> None:
    responses = iter(
        [
            {"task_id": "task-1", "status": "accepted"},
            {
                "task_id": "task-1",
                "status": "waiting_for_input",
                "pending_action": {
                    "question": "Which beneficiary?",
                    "reason_code": "missing_destination",
                    "expected_answer": {"type": "string"},
                },
            },
        ]
    )
    monkeypatch.setattr(task, "_post_json", lambda *args, **kwargs: next(responses))

    report = task.run_agent("Transfer 25 SAR.")

    assert report["status"] == "needs_input"
    assert report["result"]["question"] == "Which beneficiary?"
    assert report["needs_follow_up"] is True


def test_run_agent_signs_exact_sandbox_confirmation(monkeypatch) -> None:
    arguments = {"amount": "25.00", "currency": "SAR", "destination": "Savings"}
    resume_payloads = []
    responses = iter(
        [
            {"task_id": "task-1", "status": "accepted"},
            {
                "task_id": "task-1",
                "status": "waiting_for_confirmation",
                "pending_action": {
                    "tool_name": "transfer_funds",
                    "arguments": arguments,
                    "arguments_hash": task._arguments_hash(arguments),
                },
            },
            {},
            {
                "task_id": "task-1",
                "status": "completed",
                "final_report": {"status": "completed", "summary": "Transfer completed."},
            },
        ]
    )

    def fake_post(url, payload, secret, **kwargs):
        if url.endswith("/resume"):
            resume_payloads.append(payload)
        return next(responses)

    monkeypatch.setattr(task, "_post_json", fake_post)

    report = task.run_agent("Transfer 25 SAR to Savings.")

    token = resume_payloads[0]["authorization_token"]
    encoded, _ = token.split(".", 1)
    claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    assert report["status"] == "completed"
    assert claims["tool_name"] == "transfer_funds"
    assert claims["arguments_hash"] == task._arguments_hash(arguments)


@pytest.mark.parametrize("query", ["", "   ", None, 123])
def test_run_agent_rejects_invalid_query(query) -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        task.run_agent(query)
