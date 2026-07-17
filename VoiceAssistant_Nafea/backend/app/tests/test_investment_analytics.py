from __future__ import annotations

from decimal import Decimal

from app.dashboard import (
    calculate_investment_projection,
    calculate_portfolio_analytics,
)


def test_portfolio_analytics_aggregate_sectors_and_normalize_diversification() -> None:
    analytics = calculate_portfolio_analytics(
        [
            ("energy", "Energy", "الطاقة", Decimal("100")),
            ("financials", "Financials", "القطاع المالي", Decimal("100")),
            ("materials", "Materials", "المواد الأساسية", Decimal("100")),
        ],
        portfolio_value=Decimal("300"),
        supported_asset_count=3,
    )

    assert analytics["diversification_score"] == 100
    assert analytics["diversification_level"] == "diversified"
    assert analytics["largest_holding_percent"] == 33.3
    assert sum(
        Decimal(item["market_value_sar"])
        for item in analytics["sector_allocations"]
    ) == Decimal("300.00")
    assert round(
        sum(item["weight_percent"] for item in analytics["sector_allocations"]), 1
    ) == 100.0


def test_single_position_portfolio_is_fully_concentrated() -> None:
    analytics = calculate_portfolio_analytics(
        [("energy", "Energy", "الطاقة", Decimal("556"))],
        portfolio_value=Decimal("556"),
        supported_asset_count=3,
    )

    assert analytics["diversification_score"] == 0
    assert analytics["diversification_level"] == "focused"
    assert analytics["largest_holding_percent"] == 100.0
    assert analytics["sector_allocations"][0]["weight_percent"] == 100.0


def test_projection_with_zero_return_equals_cash_contributions() -> None:
    projection = calculate_investment_projection(
        starting_value=Decimal("5000"),
        monthly_contribution=Decimal("1000"),
        years=1,
        annual_return_percent=Decimal("0"),
    )

    assert projection["projected_value_sar"] == "17000.00"
    assert projection["total_contributions_sar"] == "17000.00"
    assert projection["estimated_growth_sar"] == "0.00"
    assert projection["milestones"][-1]["month"] == 12
    assert projection["milestones"][-1]["value_sar"] == "17000.00"
    assert projection["milestones"][-1]["contributions_sar"] == "17000.00"


def test_projection_uses_end_of_month_compounding_and_reconciles_totals() -> None:
    projection = calculate_investment_projection(
        starting_value=Decimal("5932"),
        monthly_contribution=Decimal("1000"),
        years=5,
    )

    projected = Decimal(projection["projected_value_sar"])
    contributions = Decimal(projection["total_contributions_sar"])
    growth = Decimal(projection["estimated_growth_sar"])
    assert projection["annual_return_percent"] == 7.0
    assert projection["contribution_timing"] == "end_of_month"
    assert contributions == Decimal("65932.00")
    assert abs(projected - contributions - growth) <= Decimal("0.01")
    assert Decimal(projection["milestones"][-1]["value_sar"]) == projected


def test_custom_projection_uses_live_starting_cash_custom_inputs_and_target() -> None:
    projection = calculate_investment_projection(
        starting_value=Decimal("5000"),
        one_time_contribution=Decimal("1000"),
        monthly_contribution=Decimal("500"),
        years=1,
        annual_return_percent=Decimal("0"),
        inflation_percent=Decimal("0"),
        target_amount=Decimal("12000"),
    )

    assert projection["projected_value_sar"] == "12000.00"
    assert projection["inflation_adjusted_value_sar"] == "12000.00"
    assert projection["target_achieved"] is True
    assert projection["target_gap_sar"] == "0.00"
    assert projection["target_surplus_sar"] == "0.00"
    assert projection["required_monthly_contribution_sar"] == "500.00"


def test_inflation_adjusted_value_is_lower_than_nominal_value() -> None:
    projection = calculate_investment_projection(
        starting_value=Decimal("10000"),
        monthly_contribution=Decimal("0"),
        years=10,
        annual_return_percent=Decimal("7"),
        inflation_percent=Decimal("3"),
    )

    assert Decimal(projection["inflation_adjusted_value_sar"]) < Decimal(
        projection["projected_value_sar"]
    )
