from decimal import Decimal

from agentic.tools.guard import AgentRuntimeContext, _argument_is_explicit, _clarification_copy


def test_numeric_provenance_preserves_negative_sign():
    request = "Transfer -10 SAR to Yousef"

    assert _argument_is_explicit(Decimal("-10"), request, ())
    assert not _argument_is_explicit(Decimal("10"), request, ())


def test_numeric_provenance_accepts_explicit_positive_value():
    assert _argument_is_explicit(10, "Transfer 10 SAR", ())
    assert _argument_is_explicit(Decimal("10.50"), "Transfer +10.50 SAR", ())
    assert _argument_is_explicit(2000, "Transfer 2,000 SAR", ())
    assert _argument_is_explicit(Decimal("2500.50"), "Transfer 2,500.50 SAR", ())


def test_numeric_provenance_accepts_written_amount_and_casual_plural():
    assert _argument_is_explicit(2000, "Transfer two thousand riyals", ())
    assert _argument_is_explicit(2000, "Transfer two thousands ryals", ())
    assert _argument_is_explicit(2500, "Transfer two thousand five hundred SAR", ())


def test_numeric_provenance_preserves_written_negative_sign():
    request = "Transfer negative ten SAR"

    assert _argument_is_explicit(-10, request, ())
    assert not _argument_is_explicit(10, request, ())


def test_numeric_provenance_accepts_arabic_digits_and_words():
    assert _argument_is_explicit(2000, "حوّل ٢٬٠٠٠ ريال", ())
    assert _argument_is_explicit(2000, "حوّل ألفين ريال", ())
    assert _argument_is_explicit(10, "اشتر لي عشر أسهم", ())


def test_string_provenance_requires_token_boundaries():
    assert _argument_is_explicit("Ali", "Transfer to Ali", ())
    assert not _argument_is_explicit("Ali", "Transfer to Khalid", ())
    assert not _argument_is_explicit("Ann", "Transfer to Hannah", ())


def test_arabic_destination_accepts_attached_to_preposition():
    assert _argument_is_explicit(
        "سعود",
        "حول 100 ريال لسعود",
        (),
        field_name="destination_account",
    )
    assert not _argument_is_explicit(
        "سعد",
        "حول 100 ريال لسعود",
        (),
        field_name="destination_account",
    )


def test_investment_symbol_provenance_accepts_only_configured_alias_equivalence():
    assert _argument_is_explicit("ARAMCO", "اشتر لي عشر أسهم من أرامكو", (), field_name="symbol")
    assert not _argument_is_explicit("SABIC", "اشتر لي عشر أسهم من أرامكو", (), field_name="symbol")


def test_clarification_answers_are_bound_to_the_requested_field():
    context = AgentRuntimeContext.__new__(AgentRuntimeContext)
    context.explicit_user_field_values = {"quantity": ("10",)}

    assert _argument_is_explicit(
        10,
        "اشتر أرامكو",
        context.explicit_user_field_values.get("quantity", ()),
        field_name="quantity",
    )
    assert not _argument_is_explicit(
        "10",
        "اشتر أرامكو",
        context.explicit_user_field_values.get("symbol", ()),
        field_name="symbol",
    )


def test_arabic_clarification_copy_is_localized():
    assert _clarification_copy("symbol", "اشتر أسهماً") == (
        "ما رمز الاستثمار أو اسم الشركة المطلوب؟",
        "رمز الاستثمار أو اسم الشركة",
    )
