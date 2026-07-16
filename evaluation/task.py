"""Dependency-free signed client for one-query local agent evaluation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _normalize_arguments(arguments: dict[str, Any]) -> str:
    return json.dumps(
        arguments,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _arguments_hash(arguments: dict[str, Any]) -> str:
    return hashlib.sha256(_normalize_arguments(arguments).encode("utf-8")).hexdigest()


def _confirmation_token(
    *,
    key: str,
    task_id: str,
    user_id: str,
    tenant_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "task_id": task_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "tool_name": tool_name,
        "arguments_hash": _arguments_hash(arguments),
        "nonce": secrets.token_urlsafe(24),
        "issuer": "interaction-layer",
        "confirmation_method": "standalone_evaluation",
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
    }
    encoded = _encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signature = _encode(hmac.new(key.encode(), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def _post_json(
    url: str,
    payload: dict[str, Any],
    secret: str,
    *,
    timeout: float = 10,
) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = hmac.new(
        secret.encode(), timestamp.encode("ascii") + b"." + body, hashlib.sha256
    ).hexdigest()
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Interaction-Timestamp": timestamp,
            "X-Interaction-Signature": signature,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"agent API returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("agent API is unavailable") from exc
    return json.loads(raw) if raw else {}


def run_agent(query: str) -> dict[str, Any]:
    """Submit one query and return only the safe report or required follow-up."""

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    query = query.strip()
    base_url = os.getenv("AGENTIC_BASE_URL", "http://127.0.0.1:9000").rstrip("/")
    interaction_secret = os.environ["INTERACTION_SHARED_SECRET"]
    confirmation_key = os.environ["CONFIRMATION_SIGNING_KEY"]
    timeout = float(os.getenv("AGENTIC_EVALUATION_TIMEOUT_SECONDS", "180"))
    user_id = os.getenv("AGENTIC_EVALUATION_USER_ID", "evaluation-user")
    tenant_id = os.getenv("AGENTIC_EVALUATION_TENANT_ID", "evaluation-tenant")
    request_id = str(uuid4())
    session_id = str(uuid4())
    identity = {
        "request_id": request_id,
        "session_id": session_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
    }
    accepted = _post_json(
        f"{base_url}/agentic/request",
        identity
        | {
            "language": "en",
            "natural_language_request": query,
            "original_user_message": query,
            "authorization": {
                "scopes": ["financial:read", "financial:write", "investment:trade"],
                "authenticated_at": datetime.now(timezone.utc).isoformat(),
                "assurance_level": "evaluation",
            },
            "metadata": {"source_provider": "standalone-evaluator"},
        },
        interaction_secret,
    )
    task_id = str(accepted["task_id"])
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = _post_json(
            f"{base_url}/agentic/tasks/{task_id}/status", identity, interaction_secret
        )
        state = status.get("status")
        if state in {"completed", "partially_completed", "rejected", "failed", "expired"}:
            report = status.get("final_report")
            return report if isinstance(report, dict) else {
                "status": state,
                "summary": "The task ended without a report.",
            }
        if state == "waiting_for_input":
            pending = status.get("pending_action") or {}
            return {
                "status": "needs_input",
                "result": pending,
                "needs_follow_up": True,
            }
        if state == "waiting_for_confirmation":
            pending = status.get("pending_action") or {}
            arguments = pending.get("arguments")
            tool_name = pending.get("tool_name")
            if not isinstance(arguments, dict) or not isinstance(tool_name, str):
                raise RuntimeError("agent returned an incomplete confirmation")
            expected_hash = pending.get("arguments_hash")
            if not hmac.compare_digest(str(expected_hash), _arguments_hash(arguments)):
                raise RuntimeError("agent confirmation arguments hash does not match")
            token = _confirmation_token(
                key=confirmation_key,
                task_id=task_id,
                user_id=user_id,
                tenant_id=tenant_id,
                tool_name=tool_name,
                arguments=arguments,
            )
            _post_json(
                f"{base_url}/agentic/tasks/{task_id}/resume",
                identity | {"authorization_token": token, "otp_code": "1111"},
                interaction_secret,
            )
        else:
            time.sleep(0.1)
    raise TimeoutError("agent evaluation timed out")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python task.py 'Show my balance'")
    print(json.dumps(run_agent(sys.argv[1]), ensure_ascii=False, indent=2))
