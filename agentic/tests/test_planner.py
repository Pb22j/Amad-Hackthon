from agentic_service.planner import plan_request
import json


def _action(plan):
    value = getattr(plan, "action", getattr(plan, "action_type", None))
    value = getattr(value, "value", value)
    return {"investment_order": "invest", "open_savings_and_fund": "open_savings"}.get(value, value)


def _params(plan):
    return getattr(plan, "parameters", getattr(plan, "fields", {}))


def test_english_own_account_transfer_extracts_amount_and_aliases():
    plan = plan_request("Transfer 250 SAR from my Al Rajhi account to my SNB account")
    assert _action(plan) == "own_account_transfer"
    assert _params(plan)["amount"] == "250.00"
    assert _params(plan)["source_account"] == "Al Rajhi"
    assert _params(plan)["destination_account"] == "SNB"


def test_arabic_user_transfer_with_handle():
    plan = plan_request("حوّل ١٢٥ ريال إلى @sara", "ar")
    assert _action(plan) == "user_transfer"
    assert _params(plan)["amount"] == "125.00"
    assert _params(plan)["recipient"] == "@sara"


def test_beneficiary_iban_is_normalised():
    plan = plan_request("Add beneficiary SA03 8000 0000 6080 1016 7519")
    assert _action(plan) == "add_beneficiary"
    assert _params(plan)["iban"] == "SA0380000000608010167519"


def test_gift_precedes_generic_transfer():
    plan = plan_request("Send a gift of 50 SAR to @noura")
    assert _action(plan) == "gift_transfer"
    assert _params(plan)["transfer_kind"] == "gift"


def test_qatta_extracts_participants():
    plan = plan_request("Split 300 SAR between @ali, @sara and @noura")
    assert _action(plan) == "create_qatta"
    assert _params(plan)["participants"] == ["@ali", "@sara", "@noura"]


def test_investment_extracts_tadawul_symbol_and_quantity():
    plan = plan_request("Buy 10 shares of 2222")
    assert _action(plan) == "invest"
    assert _params(plan)["symbol"] == "2222"
    assert _params(plan)["quantity"] == 10


def test_report_understands_arabic_month():
    plan = plan_request("أريد تقرير مالي لشهر يونيو 2026", "ar")
    assert _action(plan) == "monthly_report"
    assert _params(plan)["month"] == "2026-06"


def test_missing_transfer_amount_requests_input_without_guessing():
    plan = plan_request("Transfer from my Al Rajhi account to my SNB account")
    assert _action(plan) == "need_input"
    assert "amount" in plan.missing_fields


def test_store_list_and_purchase_are_distinct():
    assert _action(plan_request("Show the store catalog")) == "list_store_items"
    plan = plan_request("Buy SKU-COFFEE-01 from the store")
    assert _action(plan) == "store_purchase"
    assert _params(plan)["sku"] == "COFFEE-01"


def test_validated_model_intent_becomes_closed_agentic_plan():
    planned = json.dumps({
        "intent": "transfer_between_accounts",
        "language": "en",
        "amount": 250,
        "recipient": None,
        "source_account": "Al Rajhi",
        "destination_account": "SNB",
        "iban": None,
        "symbol": None,
        "quantity": None,
        "participants": [],
        "sku": None,
        "note": None,
        "period": None,
        "clarification_question": None,
    })
    plan = plan_request(planned)
    assert _action(plan) == "own_account_transfer"
    assert _params(plan)["amount"] == "250"
    assert _params(plan)["source_account"] == "Al Rajhi"
    assert _params(plan)["destination_account"] == "SNB"


def test_model_clarification_never_falls_through_to_mutation():
    plan = plan_request(json.dumps({
        "intent": "needs_clarification",
        "language": "ar",
        "clarification_question": "من أي حساب؟",
    }))
    assert _action(plan) == "need_input"
    assert plan.user_message == "من أي حساب؟"
