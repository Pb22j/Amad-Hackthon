from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from agentic.evals.functionality_runner import (
    FunctionalityObservation,
    ObservedToolCall,
    build_functionality_report,
    load_functionality_dataset,
    score_functionality_case,
)
from scripts.run_functionality_eval import _evaluation_config, _functional_status


DATASET = Path("agentic/evals/datasets/functionality.jsonl")


def test_functionality_evaluator_pins_every_role_to_minimax(app_config):
    openai_models = {
        role: item.model_copy(update={"provider": "openai", "model": "gpt-test"})
        for role, item in app_config.llm.models.items()
    }
    config = app_config.model_copy(
        update={"llm": app_config.llm.model_copy(update={"models": openai_models})}
    )

    evaluation_config = _evaluation_config(config, "MiniMax-M2.7")

    assert {item.provider for item in evaluation_config.llm.models.values()} == {"minimax"}
    assert {item.model for item in evaluation_config.llm.models.values()} == {"MiniMax-M2.7"}


def _perfect_observation(case):
    tools = []
    if case.expected_status != "needs_input" and case.expected_tool:
        tools = [
            ObservedToolCall(
                name=case.expected_tool,
                arguments=case.expected_arguments,
                status=case.expected_status,
                receipt_id="receipt-1" if case.expected_receipt else None,
            )
        ]
    return FunctionalityObservation(
        status=case.expected_status,
        intent=case.expected_intent,
        risk=case.expected_risk,
        tools=tools,
        confirmation_requested=case.expected_confirmation,
        clarification_requested=case.expected_status == "needs_input",
        report={"status": case.expected_status},
    )


@pytest.mark.parametrize("language", ["en", "ar"])
def test_functionality_dataset_is_balanced(language):
    cases = load_functionality_dataset(DATASET)

    assert len(cases) == 100
    assert Counter(case.language for case in cases) == Counter({"en": 50, "ar": 50})
    assert sum(case.language == language for case in cases) == 50
    assert set(Counter(case.scenario for case in cases).values()) == {10}
    assert Counter(case.expected_status for case in cases) == Counter(
        {"completed": 70, "failed": 20, "needs_input": 10}
    )
    assert not any("security" in case.category for case in cases)


def test_perfect_observations_pass_every_case_and_check():
    cases = load_functionality_dataset(DATASET)
    report = build_functionality_report(cases, [_perfect_observation(case) for case in cases])

    assert report.total == 100
    assert report.passed == 100
    assert report.checks_passed == report.checks
    assert {row.name: row.passed for row in report.languages} == {"ar": 50, "en": 50}


def test_scorer_reports_each_independent_contract_mismatch():
    case = next(
        case
        for case in load_functionality_dataset(DATASET)
        if case.scenario == "transfer_success"
    )
    observation = FunctionalityObservation(
        status="failed",
        intent="bill_payment",
        risk="medium",
        tools=[
            ObservedToolCall(
                name="pay_bill",
                arguments={"amount": "999"},
                status="failed",
            )
        ],
        confirmation_requested=False,
    )

    result = score_functionality_case(case, observation)

    assert not result.passed
    assert {mismatch.field for mismatch in result.mismatches} == {
        "status",
        "intent",
        "risk",
        "tool_sequence",
        "tool_arguments",
        "confirmation_requested",
        "receipt_present",
    }


def test_loader_rejects_duplicate_case_ids(tmp_path):
    source = DATASET.read_text(encoding="utf-8").splitlines()[0]
    path = tmp_path / "duplicate.jsonl"
    path.write_text(f"{source}\n{source}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate functionality case ids"):
        load_functionality_dataset(path)


def test_failed_tool_is_failed_even_when_report_calls_it_rejected():
    status = _functional_status(
        clarification_requested=False,
        tools=[
            ObservedToolCall(
                name="withdraw_funds",
                status="failed",
                error_code="insufficient_funds",
            )
        ],
        report={"status": "rejected"},
    )

    assert status == "failed"
