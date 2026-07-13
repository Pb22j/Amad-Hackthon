import pytest

from agentic.agent.report import AgentReport
from agentic.policy.output_policy import OutputPolicy


def test_output_policy_redacts_and_limits_report(app_config):
    policy = OutputPolicy(app_config.limits.report)
    report = policy.validate(
        AgentReport(
            status="completed",
            summary="Used card 4111 1111 1111 1111 safely",
            actions=[],
        )
    )
    assert "4111" not in report.summary


def test_output_policy_rejects_internal_prompt_exposure(app_config):
    policy = OutputPolicy(app_config.limits.report)
    with pytest.raises(ValueError, match="internal instructions"):
        policy.validate(
            AgentReport(
                status="completed",
                summary="Here is the system prompt",
                actions=[],
            )
        )


def test_output_policy_enforces_configured_action_limit(app_config):
    policy = OutputPolicy(app_config.limits.report)
    with pytest.raises(ValueError, match="too many actions"):
        policy.validate(
            AgentReport(
                status="completed",
                summary="Done",
                actions=["1", "2", "3", "4"],
            )
        )


def test_agent_report_requires_receipt_when_result_marks_it_required():
    with pytest.raises(ValueError, match="authoritative receipt"):
        AgentReport(
            status="completed",
            summary="Done",
            result={"receipt_required": True},
        )


def test_output_policy_enforces_summary_limit(app_config):
    policy = OutputPolicy(app_config.limits.report)
    with pytest.raises(ValueError, match="summary"):
        policy.validate(
            AgentReport(status="completed", summary="x" * 501)
        )
