from types import SimpleNamespace

import pytest

from agentic.agent.report import AgentReport
from agentic.agent.service import (
    _authoritative_tool_results,
    _sanitize_report_number_grounding,
    _validate_report_number_grounding,
)
from langchain_core.messages import ToolMessage


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


def test_failed_preflight_tool_result_is_authoritative_numeric_evidence():
    message = ToolMessage(
        content=(
            '{"status":"failed","summary":"Daily limit exceeded.",'
            '"data":{"requested_amount_sar":"9000.00",'
            '"spent_today_sar":"19146.00","daily_limit_sar":"20000.00"},'
            '"user_id":"admin","tenant_id":"evaluation-tenant",'
            '"receipt_id":null,"operation_id":null,"error_code":"daily_limit_exceeded"}'
        ),
        tool_call_id="preflight-1",
        name="transfer_between_accounts",
    )
    report = AgentReport(
        status="rejected",
        summary="The 9000 transfer exceeds the 20000 limit after 19146 was spent.",
    )

    _validate_report_number_grounding(
        report,
        original_request="Transfer 9000 SAR",
        executions=[],
        authoritative_tool_results=_authoritative_tool_results([message]),
    )


def test_ungrounded_reply_suggestion_is_removed_without_dropping_report():
    report = AgentReport(
        status="rejected",
        summary="The 9000 transfer exceeds the 20000 limit after 19146 was spent.",
        interaction_context={
            "response_kind": "answer",
            "user_goal": "Transfer 9000 SAR",
            "key_facts": ["The daily limit is 20000 SAR."],
            "suggested_next_steps": [
                "Try an amount below 854 SAR.",
                "Ask to view your balance.",
            ],
        },
    )
    tool_result = {
        "status": "failed",
        "summary": "Daily limit exceeded.",
        "data": {
            "requested_amount_sar": "9000.00",
            "spent_today_sar": "19146.00",
            "daily_limit_sar": "20000.00",
        },
        "user_id": "admin",
        "tenant_id": "evaluation-tenant",
        "receipt_id": None,
        "operation_id": None,
        "error_code": "daily_limit_exceeded",
    }

    sanitized = _sanitize_report_number_grounding(
        report,
        original_request="Transfer 9000 SAR",
        executions=[],
        authoritative_tool_results=[tool_result],
    )

    assert sanitized.status == "rejected"
    assert sanitized.summary == report.summary
    assert sanitized.interaction_context.suggested_next_steps == [
        "Ask to view your balance."
    ]
    assert sanitized.warnings == ["numeric_claims_removed"]


def test_completed_arabic_report_uses_truthful_fallback_when_summary_is_removed(caplog):
    report = AgentReport(
        status="completed",
        summary="إجمالي غير موثق 999 ريال.",
        interaction_context={
            "response_kind": "outcome",
            "user_goal": "معرفة التقرير الشهري",
            "key_facts": ["إجمالي المدفوعات الموثق 100 ريال."],
            "suggested_next_steps": [],
        },
    )

    sanitized = _sanitize_report_number_grounding(
        report,
        original_request="اعرض تقريري الشهري",
        executions=[execution(result={"data": {"total_paid_sar": "100.00"}})],
        language="ar",
    )

    assert sanitized.status == "completed"
    assert sanitized.summary == "تم إعداد التقرير بنجاح. تظهر التفاصيل الموثقة أدناه."
    assert sanitized.interaction_context.key_facts == [
        "إجمالي المدفوعات الموثق 100 ريال."
    ]
    assert sanitized.warnings == ["numeric_claims_removed"]
    assert "999" in caplog.text
