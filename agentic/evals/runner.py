from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from agentic.policy.engine import PolicyEngine


class SecurityEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    language: Literal["en", "ar"]
    input: str
    expected: Literal["allow", "reject", "signal"]


class SecurityEvalFailure(BaseModel):
    case_id: str
    expected: str
    actual: str


class SecurityEvalReport(BaseModel):
    total: int
    passed: int
    failures: list[SecurityEvalFailure]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 1.0


def load_security_dataset(path: str | Path) -> list[SecurityEvalCase]:
    cases: list[SecurityEvalCase] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    cases.append(SecurityEvalCase.model_validate_json(line))
                except Exception as exc:
                    raise ValueError(f"invalid eval case at line {line_number}") from exc
    return cases


def run_security_dataset(path: str | Path, policy: PolicyEngine) -> SecurityEvalReport:
    failures: list[SecurityEvalFailure] = []
    cases = load_security_dataset(path)
    for case in cases:
        decision = policy.screen_request(case.input)
        actual = "reject" if not decision.allowed else "signal" if decision.signals.detected else "allow"
        if actual != case.expected:
            failures.append(
                SecurityEvalFailure(case_id=case.id, expected=case.expected, actual=actual)
            )
    return SecurityEvalReport(
        total=len(cases),
        passed=len(cases) - len(failures),
        failures=failures,
    )

