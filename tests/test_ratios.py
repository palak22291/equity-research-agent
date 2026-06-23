import pytest
from app.calculators.ratios import RatioCalculator

# Cipla FY2025 verified reference data
CURRENT_ASSETS       = 23_288.52
CURRENT_LIABILITIES  =  5_483.96
INVENTORY            =  5_642.11
CASH                 =    799.84
TOTAL_DEBT           =    613.83
SHAREHOLDERS_EQUITY  = 31_289.25
TOTAL_ASSETS         = 37_387.04
REVENUE              = 27_145.40
EBIT                 =  6_882.81
INTEREST_EXPENSE     =     62.01
NET_INCOME           =  5_291.04
COGS                 =  8_929.00
ACCOUNTS_RECEIVABLE  =  5_506.37
TOTAL_REVENUE        = 28_409.49


@pytest.fixture
def calc():
    return RatioCalculator()


# --- Liquidity ---

def test_current_ratio(calc):
    # 23_288.52 / 5_483.96 = 4.25
    assert calc.current_ratio(CURRENT_ASSETS, CURRENT_LIABILITIES) == pytest.approx(4.25, rel=1e-2)


def test_quick_ratio(calc):
    # (799.84 + 5_506.37) / 5_483.96 = 1.15
    assert calc.quick_ratio(CASH, ACCOUNTS_RECEIVABLE, CURRENT_LIABILITIES) == pytest.approx(1.15, rel=1e-2)


def test_cash_ratio(calc):
    # 799.84 / 5_483.96 = 0.15
    assert calc.cash_ratio(CASH, CURRENT_LIABILITIES) == pytest.approx(0.15, rel=1e-2)


# --- Solvency ---

def test_debt_to_equity(calc):
    # (5_483.96 + 613.83) / 31_289.25 = 0.19
    assert calc.debt_to_equity(CURRENT_LIABILITIES, TOTAL_DEBT, SHAREHOLDERS_EQUITY) == pytest.approx(0.19, rel=1e-2)


def test_interest_coverage(calc):
    # 6_882.81 / 62.01 = 111.00
    assert calc.interest_coverage(EBIT, INTEREST_EXPENSE) == pytest.approx(111.00, rel=1e-2)


def test_debt_to_assets(calc):
    expected = round(TOTAL_DEBT / TOTAL_ASSETS, 2)
    assert calc.debt_to_assets(TOTAL_DEBT, TOTAL_ASSETS) == pytest.approx(expected, rel=1e-2)


# --- Profitability ---

def test_net_profit_margin(calc):
    # round(5_291.04 / 27_145.40, 2) = 0.19
    assert calc.net_profit_margin(NET_INCOME, REVENUE) == pytest.approx(0.19, rel=1e-2)


def test_return_on_equity(calc):
    # 5_291.04 / 31_289.25 = 0.17
    assert calc.return_on_equity(NET_INCOME, SHAREHOLDERS_EQUITY) == pytest.approx(0.17, rel=1e-2)


def test_return_on_assets(calc):
    # round(5_291.04 / 37_387.04, 2) = 0.14
    assert calc.return_on_assets(NET_INCOME, TOTAL_ASSETS) == pytest.approx(0.14, rel=1e-2)


# --- Efficiency ---

def test_asset_turnover(calc):
    assert calc.asset_turnover(TOTAL_REVENUE, TOTAL_ASSETS) == pytest.approx(0.76, rel=1e-2)


def test_inventory_turnover(calc):
    expected = round(COGS / INVENTORY, 2)
    assert calc.inventory_turnover(COGS, INVENTORY) == pytest.approx(expected, rel=1e-2)


def test_receivables_turnover(calc):
    assert calc.receivables_turnover(TOTAL_REVENUE, ACCOUNTS_RECEIVABLE) == pytest.approx(5.16, rel=1e-2)


# --- DuPont ---

def test_dupont_roe(calc):
    # (NI / Rev) × (Rev / TA) × (TA / Eq) = NI / Eq = 5_291.04 / 31_289.25 = 0.17
    net_profit_margin = NET_INCOME / REVENUE
    asset_turnover    = REVENUE / TOTAL_ASSETS
    equity_multiplier = TOTAL_ASSETS / SHAREHOLDERS_EQUITY
    expected = net_profit_margin * asset_turnover * equity_multiplier
    assert calc.dupont_roe(net_profit_margin, asset_turnover, equity_multiplier) == pytest.approx(expected, rel=1e-2)


# --- Zero-division guards ---

def test_zero_division_raises_value_error(calc):
    with pytest.raises(ValueError):
        calc.current_ratio(CURRENT_ASSETS, 0)
    with pytest.raises(ValueError):
        calc.quick_ratio(CASH, ACCOUNTS_RECEIVABLE, 0)
    with pytest.raises(ValueError):
        calc.cash_ratio(CASH, 0)
    with pytest.raises(ValueError):
        calc.debt_to_equity(CURRENT_LIABILITIES, TOTAL_DEBT, 0)
    with pytest.raises(ValueError):
        calc.interest_coverage(EBIT, 0)
    with pytest.raises(ValueError):
        calc.debt_to_assets(TOTAL_DEBT, 0)
    with pytest.raises(ValueError):
        calc.net_profit_margin(NET_INCOME, 0)
    with pytest.raises(ValueError):
        calc.return_on_equity(NET_INCOME, 0)
    with pytest.raises(ValueError):
        calc.return_on_assets(NET_INCOME, 0)
    with pytest.raises(ValueError):
        calc.asset_turnover(REVENUE, 0)
    with pytest.raises(ValueError):
        calc.inventory_turnover(COGS, 0)
    with pytest.raises(ValueError):
        calc.receivables_turnover(REVENUE, 0)
