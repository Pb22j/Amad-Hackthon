"""Exact scoring primitives for end-to-end financial functionality evaluations."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


FunctionalStatus = Literal["completed", "failed", "needs_input"]


class FunctionalityEvalCase(BaseModel):
    """One user-visible workflow and its exact functional contract."""

    model_config = ConfigDict(extra="forbid")

    id: str
    language: Literal["en", "ar"]
    category: str
    scenario: str
    input: str
    expected_status: FunctionalStatus
    expected_intent: str
    expected_risk: str
    expected_tool: str | None = None
    expected_arguments: dict[str, Any] = Field(default_factory=dict)
    expected_confirmation: bool
    expected_receipt: bool


class ObservedToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: str | None = None
    receipt_id: str | None = None
    error_code: str | None = None


class FunctionalityObservation(BaseModel):
    """Auditable facts collected from task state, events, and tool executions."""

    model_config = ConfigDict(extra="forbid")

    status: FunctionalStatus
    intent: str | None = None
    risk: str | None = None
    tools: list[ObservedToolCall] = Field(default_factory=list)
    confirmation_requested: bool = False
    clarification_requested: bool = False
    report: dict[str, Any] | None = None


class FunctionalityMismatch(BaseModel):
    field: str
    expected: Any
    actual: Any


class FunctionalityCaseResult(BaseModel):
    case_id: str
    category: str
    scenario: str
    language: str
    passed: bool
    checks: int
    checks_passed: int
    mismatches: list[FunctionalityMismatch]
    observation: FunctionalityObservation


class FunctionalityBreakdown(BaseModel):
    name: str
    total: int
    passed: int

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 1.0


class FunctionalityEvalReport(BaseModel):
    total: int
    passed: int
    checks: int
    checks_passed: int
    results: list[FunctionalityCaseResult]
    categories: list[FunctionalityBreakdown]
    scenarios: list[FunctionalityBreakdown]
    languages: list[FunctionalityBreakdown]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 1.0

    @property
    def check_rate(self) -> float:
        return self.checks_passed / self.checks if self.checks else 1.0


def load_functionality_dataset(path: str | Path) -> list[FunctionalityEvalCase]:
    cases: list[FunctionalityEvalCase] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                cases.append(FunctionalityEvalCase.model_validate_json(line))
            except Exception as exc:
                raise ValueError(f"invalid functionality case at line {line_number}") from exc
    duplicates = sorted(case_id for case_id, count in Counter(c.id for c in cases).items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate functionality case ids: {', '.join(duplicates)}")
    return cases


def _normalized(value: Any) -> Any:
    """Make numeric/string representations comparable without fuzzy matching."""

    if isinstance(value, dict):
        return {key: _normalized(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalized(item) for item in value]
    if isinstance(value, (int, float)):
        return str(value)
    return value


def _arguments_contain(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    normalized_actual = _normalized(actual)
    normalized_expected = _normalized(expected)
    return all(
        key in normalized_actual and normalized_actual[key] == value
        for key, value in normalized_expected.items()
    )


def score_functionality_case(
    case: FunctionalityEvalCase,
    observation: FunctionalityObservation,
) -> FunctionalityCaseResult:
    mismatches: list[FunctionalityMismatch] = []
    checks = 0

    def check(field: str, expected: Any, actual: Any, *, matches: bool | None = None) -> None:
        nonlocal checks
        checks += 1
        if matches if matches is not None else expected == actual:
            return
        mismatches.append(
            FunctionalityMismatch(field=field, expected=expected, actual=actual)
        )

    check("status", case.expected_status, observation.status)
    check("intent", case.expected_intent, observation.intent)
    check("risk", case.expected_risk, observation.risk)

    if case.expected_status == "needs_input":
        check("clarification_requested", True, observation.clarification_requested)
        check("financial_tool_calls", [], [tool.name for tool in observation.tools])
    else:
        expected_tools = [case.expected_tool] if case.expected_tool else []
        actual_tools = [tool.name for tool in observation.tools]
        check("tool_sequence", expected_tools, actual_tools)
        if case.expected_tool and observation.tools:
            check(
                "tool_arguments",
                case.expected_arguments,
                observation.tools[0].arguments,
                matches=_arguments_contain(
                    observation.tools[0].arguments, case.expected_arguments
                ),
            )

    check(
        "confirmation_requested",
        case.expected_confirmation,
        observation.confirmation_requested,
    )
    has_receipt = any(tool.receipt_id for tool in observation.tools)
    check("receipt_present", case.expected_receipt, has_receipt)

    return FunctionalityCaseResult(
        case_id=case.id,
        category=case.category,
        scenario=case.scenario,
        language=case.language,
        passed=not mismatches,
        checks=checks,
        checks_passed=checks - len(mismatches),
        mismatches=mismatches,
        observation=observation,
    )


def _breakdown(
    results: list[FunctionalityCaseResult], attribute: str
) -> list[FunctionalityBreakdown]:
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    for result in results:
        name = str(getattr(result, attribute))
        totals[name]["total"] += 1
        totals[name]["passed"] += int(result.passed)
    return [
        FunctionalityBreakdown(name=name, **counts)
        for name, counts in sorted(totals.items())
    ]


def build_functionality_report(
    cases: list[FunctionalityEvalCase],
    observations: list[FunctionalityObservation],
) -> FunctionalityEvalReport:
    if len(cases) != len(observations):
        raise ValueError("every functionality case requires exactly one observation")
    results = [
        score_functionality_case(case, observation)
        for case, observation in zip(cases, observations, strict=True)
    ]
    return FunctionalityEvalReport(
        total=len(results),
        passed=sum(result.passed for result in results),
        checks=sum(result.checks for result in results),
        checks_passed=sum(result.checks_passed for result in results),
        results=results,
        categories=_breakdown(results, "category"),
        scenarios=_breakdown(results, "scenario"),
        languages=_breakdown(results, "language"),
    )


def write_functionality_report(report: FunctionalityEvalReport, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
