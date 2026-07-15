from decimal import Decimal

from agentic.tools.guard import _argument_is_explicit


def test_numeric_provenance_preserves_negative_sign():
    request = "Transfer -10 SAR to Yousef"

    assert _argument_is_explicit(Decimal("-10"), request, ())
    assert not _argument_is_explicit(Decimal("10"), request, ())


def test_numeric_provenance_accepts_explicit_positive_value():
    assert _argument_is_explicit(10, "Transfer 10 SAR", ())
    assert _argument_is_explicit(Decimal("10.50"), "Transfer +10.50 SAR", ())


def test_numeric_provenance_accepts_written_amount_and_casual_plural():
    assert _argument_is_explicit(2000, "Transfer two thousand riyals", ())
    assert _argument_is_explicit(2000, "Transfer two thousands ryals", ())
    assert _argument_is_explicit(2500, "Transfer two thousand five hundred SAR", ())


def test_numeric_provenance_preserves_written_negative_sign():
    request = "Transfer negative ten SAR"

    assert _argument_is_explicit(-10, request, ())
    assert not _argument_is_explicit(10, request, ())
