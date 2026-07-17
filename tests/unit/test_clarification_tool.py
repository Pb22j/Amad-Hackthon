import pytest

from agentic.tools.clarification import normalize_expected_answer


def test_expected_answer_schema_gets_safe_ui_defaults():
    assert normalize_expected_answer(
        {"type": "string", "field": "source_account", "label": "Source account"}
    ) == {
        "type": "string",
        "field": "source_account",
        "label": "Source account",
        "minLength": 1,
        "maxLength": 500,
    }


@pytest.mark.parametrize("field", ["otp", "access_token", "account_password"])
def test_expected_answer_schema_rejects_sensitive_fields(field):
    with pytest.raises(ValueError, match="credentials or secrets"):
        normalize_expected_answer({"type": "string", "field": field})


def test_expected_answer_schema_supports_bounded_choices():
    schema = normalize_expected_answer(
        {"type": "string", "field": "account", "enum": ["Checking", "Savings"]}
    )
    assert schema["enum"] == ["Checking", "Savings"]
