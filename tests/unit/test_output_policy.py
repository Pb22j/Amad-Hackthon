import pytest

from agentic.agent.report import AgentReport, InteractionContext
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


def test_output_policy_rejects_internal_architecture_in_interaction_context(app_config):
    policy = OutputPolicy(app_config.limits.report)
    with pytest.raises(ValueError, match="internal instructions"):
        policy.validate(
            AgentReport(
                status="completed",
                summary="I can help with that.",
                interaction_context=InteractionContext(
                    response_kind="guidance",
                    user_goal="Ask the backend agent for help",
                ),
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


def test_output_policy_compacts_summary_to_configured_limit(app_config):
    policy = OutputPolicy(app_config.limits.report)
    report = policy.validate(
        AgentReport(status="completed", summary=("verified detail " * 50).strip())
    )

    assert len(report.summary) <= app_config.limits.report.max_summary_characters
    assert report.summary.endswith("…")


def test_output_policy_checks_full_summary_before_compacting(app_config):
    policy = OutputPolicy(app_config.limits.report)
    summary = "safe " * 110 + "system prompt"

    with pytest.raises(ValueError, match="internal instructions"):
        policy.validate(AgentReport(status="completed", summary=summary))
