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


def test_account_number_provenance_ignores_grouping_whitespace_and_dashes():
    # Banks display IBANs grouped while the model passes them compacted (and
    # vice versa). Either formatting must satisfy provenance so the guard does
    # not loop asking for the same IBAN.
    grouped_request = "اضف مستفيد ورقم الايبان SA44 2000 0001 2345 6789 1234"
    assert _argument_is_explicit(
        "SA4420000001234567891234",
        grouped_request,
        (),
        field_name="benefit_account_number",
    )
    compact_request = "اضف مستفيد ورقم الايبان SA4420000001234567891234"
    assert _argument_is_explicit(
        "SA44 2000 0001 2345 6789 1234",
        compact_request,
        (),
        field_name="benefit_account_number",
    )
    # Supplied through an authenticated clarification answer that was grouped.
    assert _argument_is_explicit(
        "SA4420000001234567891234",
        "اضف مستفيد",
        ("SA44 2000 0001 2345 6789 1234",),
        field_name="benefit_account_number",
    )


def test_string_provenance_folds_arabic_indic_digits():
    # Numeric string fields (bill last-four-digits keep leading zeros, so they
    # are strings) must match whether the user typed Arabic-Indic or ASCII
    # digits; the schema forces the model to ASCII.
    assert _argument_is_explicit(
        "5544",
        "ادفع فاتورة رقمها ٥٥٤٤",
        (),
        field_name="last_four_digits",
    )
    # A different four digits must still be rejected.
    assert not _argument_is_explicit(
        "1234",
        "ادفع فاتورة رقمها ٥٥٤٤",
        (),
        field_name="last_four_digits",
    )


def test_string_provenance_accepts_glued_arabic_proclitics():
    # Arabic glues short prepositions to the following noun, so "transfer to
    # Mohammed" is written "حوّل لمحمد" with the destination "محمد" attached to
    # "لـ". The name is genuinely present and must satisfy provenance.
    assert _argument_is_explicit("محمد", "حوّل 50 لمحمد", (), field_name="destination_account")
    assert _argument_is_explicit("أحمد", "ادفع لأحمد", (), field_name="destination")
    assert _argument_is_explicit("خالد", "حوّل ولخالد", ())
    # A different name is still rejected even with a proclitic present.
    assert not _argument_is_explicit("محمد", "حوّل لسعد", (), field_name="destination_account")


def test_string_provenance_folds_arabic_letter_variants():
    # Hamza, taa marbuta, and alef maqsura variants are cosmetic — the bank
    # database already unifies them when resolving saved names, so the guard
    # must not loop asking for a name the user really stated.
    assert _argument_is_explicit(
        "احمد", "اضف مستفيد اسمه أحمد", (), field_name="full_name_of_benefit_account"
    )
    assert _argument_is_explicit(
        "فاطمة", "حول إلى فاطمه 500", (), field_name="destination"
    )
    assert _argument_is_explicit(
        "عيسي", "قطة مع عيسى", (), field_name="participants"
    )
    # A genuinely different name is still rejected.
    assert not _argument_is_explicit(
        "خالد", "حول إلى أحمد", (), field_name="destination"
    )


def test_account_number_provenance_still_rejects_absent_number():
    # An account number the user never stated must remain blocked.
    request = "اضف مستفيد ورقم الايبان SA44 2000 0001 2345 6789 1234"
    assert not _argument_is_explicit(
        "SA9988776655443322110099",
        request,
        (),
        field_name="benefit_account_number",
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
