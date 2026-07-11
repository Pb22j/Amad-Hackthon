"""Configuration for the agentic service.

No secret is logged or persisted by this module.  The live banking adapter
uses references to externally managed secrets, never values from SQLite.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class AgenticSettings:
    """Environment backed service settings with safe local defaults."""

    host: str = "127.0.0.1"
    port: int = 8090
    database_path: str = "agentic/data/agentic.sqlite3"
    provider_mode: str = "mock"
    banking_provider: str = "mock"
    planner_provider: str = "heuristic"
    approval_mode: str = "auto_mock"
    interaction_callback_url: str = ""
    interaction_webhook_secret: str = ""
    request_webhook_secret: str = ""
    task_runner_enabled: bool = True
    max_gift_message_length: int = 180

    @classmethod
    def from_env(cls) -> "AgenticSettings":
        port_raw = os.getenv("AGENTIC_PORT", "8090")
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise ValueError("AGENTIC_PORT must be an integer") from exc
        if not 1 <= port <= 65535:
            raise ValueError("AGENTIC_PORT must be between 1 and 65535")

        backend = os.getenv(
            "AGENTIC_PROVIDER_MODE",
            os.getenv("AGENTIC_BANKING_BACKEND", os.getenv("AGENTIC_BACKEND", "mock")),
        ).strip().lower()
        # ``AGENTIC_BANKING_BACKEND=saudi_open_banking`` is a convenient
        # single-value selector; the explicit mode/provider pair remains
        # available for deployments with several contracted profiles.
        mode = "live" if backend in {"live", "saudi_open_banking", "saudi-ob"} else backend
        if mode not in {"mock", "live"}:
            raise ValueError("AGENTIC_PROVIDER_MODE must be 'mock' or 'live'")
        default_provider = "mock" if mode == "mock" else "saudi_open_banking"
        banking_provider = os.getenv("AGENTIC_BANKING_PROVIDER", default_provider).strip().lower().replace("-", "_")
        if mode == "mock" and banking_provider != "mock":
            raise ValueError("AGENTIC_BANKING_PROVIDER must be 'mock' when AGENTIC_PROVIDER_MODE=mock")
        if mode == "live" and banking_provider not in {"saudi_open_banking", "saudi_ob"}:
            raise ValueError("AGENTIC_BANKING_PROVIDER must be 'saudi_open_banking' in live mode")
        approval_mode = os.getenv("AGENTIC_APPROVAL_MODE", "auto_mock").strip().lower()
        if approval_mode not in {"auto_mock", "explicit"}:
            raise ValueError("AGENTIC_APPROVAL_MODE must be 'auto_mock' or 'explicit'")
        # Auto approval is a development-only convenience.  Making this
        # invalid at startup protects a live provider from accidental use.
        if mode == "live" and approval_mode == "auto_mock":
            raise ValueError("AGENTIC_APPROVAL_MODE=auto_mock is forbidden in live mode")

        database_path = os.getenv("AGENTIC_DATABASE_PATH", "agentic/data/agentic.sqlite3")
        return cls(
            host=os.getenv("AGENTIC_HOST", "127.0.0.1"),
            port=port,
            database_path=database_path,
            provider_mode=mode,
            banking_provider="saudi_open_banking" if banking_provider == "saudi_ob" else banking_provider,
            planner_provider=os.getenv("AGENTIC_PLANNER_PROVIDER", os.getenv("AGENTIC_PLANNER", "heuristic")).strip().lower(),
            approval_mode=approval_mode,
            interaction_callback_url=os.getenv("INTERACTION_AGENTIC_CALLBACK_URL", os.getenv("AGENTIC_NOTIFY_URL", "")).strip(),
            interaction_webhook_secret=os.getenv("AGENTIC_INTERACTION_WEBHOOK_SECRET", os.getenv("AGENTIC_NOTIFY_SECRET", "")),
            request_webhook_secret=os.getenv(
                "AGENTIC_REQUEST_WEBHOOK_SECRET",
                os.getenv("AGENTIC_WEBHOOK_SECRET", os.getenv("AGENTIC_SHARED_SECRET", "")),
            ),
            task_runner_enabled=_bool(os.getenv("AGENTIC_TASK_RUNNER_ENABLED"), True),
            max_gift_message_length=int(os.getenv("AGENTIC_MAX_GIFT_MESSAGE_LENGTH", "180")),
        )

    def ensure_data_directory(self) -> None:
        """Create the configured local database parent when it has one."""
        if self.database_path != ":memory:":
            Path(self.database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
