import pytest
from app.calculators.cost_of_capital import CostOfCapitalCalculator

# Cipla FY2025 verified reference data
RISK_FREE_RATE       = 0.065
BETA                 = 0.446835987521501
MARKET_RETURN        = 0.10836452656983371
PRE_TAX_COST_OF_DEBT = 0.06836
TAX_RATE             = 0.2619549409382591
BOOK_VALUE_DEBT      = 613.83
BOOK_VALUE_EQUITY    = 31_289.25

# Professor's 4-year median weights (FY2022–FY2025) used in WACC.
# Computed as median(Wd) and median(We) independently across years;
# single-year FY2025 weights (0.019240 / 0.980760) differ from these.
MEDIAN_WD = 0.02533028875713296
MEDIAN_WE = 0.9807595379505678


@pytest.fixture
def calc():
    return CostOfCapitalCalculator()


def test_capm_cost_of_equity(calc):
    # Rf + Beta × (Rm - Rf) = 0.065 + 0.4468 × 0.0434 = 0.084377
    assert calc.capm_cost_of_equity(
        RISK_FREE_RATE, BETA, MARKET_RETURN
    ) == pytest.approx(0.084377, rel=1e-4)


def test_post_tax_cost_of_debt(calc):
    # 0.06836 × (1 - 0.2620) = 0.050453
    assert calc.post_tax_cost_of_debt(
        PRE_TAX_COST_OF_DEBT, TAX_RATE
    ) == pytest.approx(0.050453, rel=1e-4)


def test_weight_of_debt(calc):
    # FY2025 single-year weight: 613.83 / (613.83 + 31289.25) = 0.019240
    # Note: professor's WACC uses 4-year median Wd = 0.025330, not this value
    expected = round(BOOK_VALUE_DEBT / (BOOK_VALUE_DEBT + BOOK_VALUE_EQUITY), 6)
    assert calc.weight_of_debt(BOOK_VALUE_DEBT, BOOK_VALUE_EQUITY) == pytest.approx(expected, rel=1e-4)


def test_weight_of_equity(calc):
    # FY2025 single-year weight: 31289.25 / (613.83 + 31289.25) = 0.980760
    expected = round(BOOK_VALUE_EQUITY / (BOOK_VALUE_DEBT + BOOK_VALUE_EQUITY), 6)
    assert calc.weight_of_equity(BOOK_VALUE_DEBT, BOOK_VALUE_EQUITY) == pytest.approx(expected, rel=1e-4)


def test_wacc(calc):
    # Professor used 4-year median Wd/We (not FY2025 single-year weights).
    # Ke and Kd are computed from the calculator and passed in.
    ke = calc.capm_cost_of_equity(RISK_FREE_RATE, BETA, MARKET_RETURN)
    kd = calc.post_tax_cost_of_debt(PRE_TAX_COST_OF_DEBT, TAX_RATE)
    assert calc.wacc(MEDIAN_WD, kd, MEDIAN_WE, ke) == pytest.approx(0.084031, abs=1e-5)


def test_zero_division_raises_value_error(calc):
    with pytest.raises(ValueError):
        calc.weight_of_debt(0, 0)
    with pytest.raises(ValueError):
        calc.weight_of_equity(0, 0)
