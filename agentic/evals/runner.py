"""Deterministic runner for multilingual adversarial security datasets.

Cases are labelled with the behaviour the security policy is *intended* to produce, not with
the behaviour the current detector happens to produce. A case that the detector cannot yet
satisfy carries a `known_gap` reason: it is reported separately from a regression so the
dataset can record an honest target without turning the suite red on a documented weakness.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from agentic.policy.engine import PolicyEngine


Outcome = Literal["allow", "reject", "signal"]


class SecurityEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
    language: Literal["en", "ar", "mixed"]
    input: str
    expected: Outcome
    # Present when the detector is known not to reach `expected` yet. The text is the reason,
    # which is surfaced in the report so a gap can never be silently carried.
    known_gap: str | None = None
    # Why an unmitigated-looking gap is not exploitable end to end, if that is the case.
    mitigation: str | None = None


class SecurityEvalFailure(BaseModel):
    case_id: str
    category: str
    language: str
    input: str
    expected: str
    actual: str
    known_gap: str | None = None
    mitigation: str | None = None


class CategoryBreakdown(BaseModel):
    category: str
    total: int
    passed: int
    known_gaps: int
    regressions: int

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 1.0


class SecurityEvalReport(BaseModel):
    total: int
    passed: int
    # Cases that missed `expected` without a `known_gap` marker. These fail the suite.
    failures: list[SecurityEvalFailure]
    # Cases that missed `expected` and are documented as gaps. Reported, not fatal.
    known_gaps: list[SecurityEvalFailure]
    # Cases marked `known_gap` that now reach `expected`; the marker should be removed.
    fixed_gaps: list[str]
    categories: list[CategoryBreakdown]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 1.0

    @property
    def regression_free(self) -> bool:
        return not self.failures


def load_security_dataset(path: str | Path) -> list[SecurityEvalCase]:
    cases: list[SecurityEvalCase] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    cases.append(SecurityEvalCase.model_validate_json(line))
                except Exception as exc:
                    raise ValueError(f"invalid eval case at line {line_number}") from exc
    identifiers = [case.id for case in cases]
    duplicates = sorted({key for key in identifiers if identifiers.count(key) > 1})
    if duplicates:
        raise ValueError(f"duplicate eval case ids: {', '.join(duplicates)}")
    return cases


def screen_case(case: SecurityEvalCase, policy: PolicyEngine) -> Outcome:
    decision = policy.screen_request(case.input)
    if not decision.allowed:
        return "reject"
    return "signal" if decision.signals.detected else "allow"


def run_security_dataset(path: str | Path, policy: PolicyEngine) -> SecurityEvalReport:
    cases = load_security_dataset(path)
    failures: list[SecurityEvalFailure] = []
    known_gaps: list[SecurityEvalFailure] = []
    fixed_gaps: list[str] = []
    passed = 0
    tally: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "passed": 0, "known_gaps": 0, "regressions": 0}
    )

    for case in cases:
        actual = screen_case(case, policy)
        bucket = tally[case.category]
        bucket["total"] += 1
        if actual == case.expected:
            passed += 1
            bucket["passed"] += 1
            if case.known_gap:
                fixed_gaps.append(case.id)
            continue
        failure = SecurityEvalFailure(
            case_id=case.id,
            category=case.category,
            language=case.language,
            input=case.input,
            expected=case.expected,
            actual=actual,
            known_gap=case.known_gap,
            mitigation=case.mitigation,
        )
        if case.known_gap:
            known_gaps.append(failure)
            bucket["known_gaps"] += 1
        else:
            failures.append(failure)
            bucket["regressions"] += 1

    categories = [
        CategoryBreakdown(category=name, **counts) for name, counts in sorted(tally.items())
    ]
    return SecurityEvalReport(
        total=len(cases),
        passed=passed,
        failures=failures,
        known_gaps=known_gaps,
        fixed_gaps=fixed_gaps,
        categories=categories,
    )
