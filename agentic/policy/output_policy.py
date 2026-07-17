"""Validation connecting final success claims to authoritative tool receipts."""

from __future__ import annotations

import json

from agentic.agent.report import AgentReport
from agentic.config.loader import ReportLimits
from agentic.security.redaction import redact


FORBIDDEN_OUTPUT_PHRASES = (
    "system prompt",
    "developer message",
    "hidden instruction",
    "chain of thought",
    "agentic layer",
    "interaction agent",
    "backend agent",
    "another agent",
    "tool call",
    "request_user_input",
    "capability catalog",
    "backend",
    "internal service",
    "delegation",
)


def _compact_summary(summary: str, limit: int) -> str:
    """Fit model prose to the transport limit without failing the task."""

    if len(summary) <= limit:
        return summary
    prefix = summary[: limit - 1].rstrip()
    word_boundary = prefix.rfind(" ")
    if word_boundary >= limit // 2:
        prefix = prefix[:word_boundary].rstrip()
    return f"{prefix}…"


class OutputPolicy:
    def __init__(self, limits: ReportLimits) -> None:
        self.limits = limits

    def validate(self, report: AgentReport) -> AgentReport:
        safe = AgentReport.model_validate(redact(report.model_dump(mode="json")))
        if len(safe.actions) > self.limits.max_actions:
            raise ValueError("report contains too many actions")
        combined = json.dumps(
            {
                "summary": safe.summary,
                "actions": safe.actions,
                "interaction_context": safe.interaction_context.model_dump(mode="json"),
            },
            ensure_ascii=False,
        ).lower()
        if any(phrase in combined for phrase in FORBIDDEN_OUTPUT_PHRASES):
            raise ValueError("report attempts to expose internal instructions")
        if len(safe.summary) <= self.limits.max_summary_characters:
            return safe
        return safe.model_copy(
            update={
                "summary": _compact_summary(
                    safe.summary, self.limits.max_summary_characters
                )
            }
        )
