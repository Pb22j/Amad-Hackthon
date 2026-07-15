from types import SimpleNamespace

import pytest

from agentic.agent.report import AgentReport
from agentic.agent.service import _validate_report_number_grounding


def execution(*, arguments=None, result=None):
    return SimpleNamespace(arguments=arguments or {}, result=result or {})


def test_report_numbers_must_come_from_request_or_tool_result():
    report = AgentReport(status="completed", summary="Your balance is 25,431.50 SAR.")

    _validate_report_number_grounding(
        report,
        original_request="What is my balance?",
        executions=[execution(result={"data": {"balance_sar": "25431.50"}})],
    )


def test_report_rejects_model_created_financial_arithmetic():
    report = AgentReport(
        status="completed",
        summary="Your net worth is 24867.65 after subtracting bills of 563.85.",
    )

    with pytest.raises(ValueError, match="not grounded"):
        _validate_report_number_grounding(
            report,
            original_request="What is my net worth?",
            executions=[execution(result={"data": {"balance_sar": "25431.50"}})],
        )


def test_requested_number_is_valid_evidence():
    report = AgentReport(status="completed", summary="No transaction was made for 10 SAR.")

    _validate_report_number_grounding(
        report,
        original_request="Transfer 10 SAR",
        executions=[execution(result={"status": "failed"})],
    )
