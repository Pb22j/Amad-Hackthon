"""Validation connecting final success claims to authoritative tool receipts."""

from __future__ import annotations

from agentic.agent.report import AgentReport
from agentic.config.loader import ReportLimits
from agentic.security.redaction import redact


FORBIDDEN_OUTPUT_PHRASES = (
    "system prompt",
    "developer message",
    "hidden instruction",
    "chain of thought",
)


class OutputPolicy:
    def __init__(self, limits: ReportLimits) -> None:
        self.limits = limits

    def validate(self, report: AgentReport) -> AgentReport:
        safe = AgentReport.model_validate(redact(report.model_dump(mode="json")))
        if len(safe.summary) > self.limits.max_summary_characters:
            raise ValueError("report summary exceeds the configured limit")
        if len(safe.actions) > self.limits.max_actions:
            raise ValueError("report contains too many actions")
        combined = " ".join([safe.summary, *safe.actions]).lower()
        if any(phrase in combined for phrase in FORBIDDEN_OUTPUT_PHRASES):
            raise ValueError("report attempts to expose internal instructions")
        return safe
