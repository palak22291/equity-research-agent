import pytest
from app.calculators.dcf import DCFCalculator

# Cipla FY2025 verified reference data
BASE_FCFE           =  1_571.02
BASE_FCFF           =  1_675.01
GROWTH_RATE         =  0.09
KE                  =  0.08437683105323401
WACC                =  0.0840313648229122
TERMINAL_GROWTH_RATE=  0.08
SHARES_OUTSTANDING  =  807_617_120
MARKET_PRICE        =  1_441

# Financial data is in crore INR; shares_outstanding is absolute.
# Divide by 10_000_000 to express shares in crore so units are consistent
# with the crore-denominated equity value.
SHARES_CRORE = SHARES_OUTSTANDING / 10_000_000   # 80.761712 crore shares


@pytest.fixture
def calc():
    return DCFCalculator()


# --- Forecast ---

def test_forecast_cashflows(calc):
    fcfe = calc.forecast_cashflows(BASE_FCFE, GROWTH_RATE, 3)
    assert fcfe[0] == pytest.approx(1712.41, abs=0.01)
    assert fcfe[1] == pytest.approx(1866.53, abs=0.01)
    assert fcfe[2] == pytest.approx(2034.52, abs=0.01)


# --- Present Value ---

def test_present_value(calc):
    fcfe = calc.forecast_cashflows(BASE_FCFE, GROWTH_RATE, 3)
    assert calc.present_value(fcfe[0], KE, 1) == pytest.approx(1579.17, abs=0.01)
    assert calc.present_value(fcfe[1], KE, 2) == pytest.approx(1587.36, abs=0.01)
    assert calc.present_value(fcfe[2], KE, 3) == pytest.approx(1595.59, abs=0.01)


# --- Terminal Value ---

def test_terminal_value(calc):
    # Uses unrounded year-3 forecast so TV precision matches professor Excel
    fcfe = calc.forecast_cashflows(BASE_FCFE, GROWTH_RATE, 3)
    assert calc.terminal_value(fcfe[-1], TERMINAL_GROWTH_RATE, KE) == pytest.approx(502024.81, abs=0.1)


def test_terminal_value_raises_when_discount_le_growth(calc):
    with pytest.raises(ValueError):
        calc.terminal_value(2000.0, growth_rate=0.10, discount_rate=0.08)
    with pytest.raises(ValueError):
        calc.terminal_value(2000.0, growth_rate=0.10, discount_rate=0.10)


# --- PV of Terminal Value ---

def test_pv_of_terminal_value(calc):
    assert calc.pv_of_terminal_value(502024.81, KE, 3) == pytest.approx(393717.29, abs=0.1)


# --- Intrinsic Equity Value ---

def test_intrinsic_equity_value(calc):
    fcfe = calc.forecast_cashflows(BASE_FCFE, GROWTH_RATE, 3)
    assert calc.intrinsic_equity_value(fcfe, KE, TERMINAL_GROWTH_RATE) == pytest.approx(398479.40, abs=1.0)


# --- Intrinsic Share Price ---

def test_intrinsic_share_price(calc):
    fcfe = calc.forecast_cashflows(BASE_FCFE, GROWTH_RATE, 3)
    eq_val = calc.intrinsic_equity_value(fcfe, KE, TERMINAL_GROWTH_RATE)
    assert calc.intrinsic_share_price(eq_val, SHARES_CRORE) == pytest.approx(4934.01, abs=0.1)


def test_intrinsic_share_price_raises_on_zero_shares(calc):
    with pytest.raises(ValueError):
        calc.intrinsic_share_price(398479.40, 0)


# --- Intrinsic Enterprise Value ---

def test_intrinsic_enterprise_value(calc):
    fcff = calc.forecast_cashflows(BASE_FCFF, GROWTH_RATE, 3)
    assert calc.intrinsic_enterprise_value(fcff, WACC, TERMINAL_GROWTH_RATE) == pytest.approx(461268.36, abs=1.0)


# --- Valuation Verdict ---

def test_valuation_verdict_undervalued(calc):
    assert calc.valuation_verdict(4934.01, MARKET_PRICE) == "Undervalued"


def test_valuation_verdict_overvalued(calc):
    assert calc.valuation_verdict(100.0, MARKET_PRICE) == "Overvalued"


def test_valuation_verdict_fairly_valued(calc):
    assert calc.valuation_verdict(MARKET_PRICE * 1.05, MARKET_PRICE) == "Fairly Valued"


# --- Sensitivity Analysis ---

def test_sensitivity_analysis(calc):
    ke_vals = [0.0801, 0.0844, 0.0901, 0.09]
    tg_vals = [0.07, 0.08, 0.09]
    result = calc.sensitivity_analysis(
        1571.02, ke_vals, tg_vals, 80.761712, 0.09, years=3
    )

    # Verified cells from professor sensitivity table
    assert result[0.0844][0.08] == pytest.approx(4908.03,    abs=5.0)
    assert result[0.0844][0.07] == pytest.approx(1526.90,    abs=5.0)
    assert result[0.0901][0.08] == pytest.approx(2138.16,    abs=5.0)
    assert result[0.0801][0.08] == pytest.approx(215976.55,  abs=100.0)

    # ke=0.09, tg=0.09: ke == tg — Gordon Growth undefined, must return None
    assert result[0.09][0.09] is None
