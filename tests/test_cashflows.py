import pytest
from app.calculators.cashflows import CashFlowCalculator

# Cipla FY2025 verified reference data
NET_INCOME        =  5_291.04
NON_CASH_EXPENSES =  1_106.95
INCREASE_IN_CA    =  3_847.11
INCREASE_IN_CL    =    238.19
INTEREST          =     62.01
TAX_RATE          =  0.22427867698803655
CAPEX             =  1_162.16
CFO               =  2_789.07
OCF               =  2_789.07
NET_BORROWING     =    -55.89
EBIT              =  6_882.81
NOPAT_VALUE       =  5_339.14

EXPECTED_FCFF     =  1_675.01
EXPECTED_FCFE     =  1_571.02
EXPECTED_NOPAT    =  5_339.14


@pytest.fixture
def calc():
    return CashFlowCalculator()


# --- Helper ---

def test_nopat(calc):
    assert calc.nopat(EBIT, TAX_RATE) == pytest.approx(EXPECTED_NOPAT, abs=0.1)


# --- FCFF ---

def test_fcff_from_net_income(calc):
    assert calc.fcff_from_net_income(
        NET_INCOME, NON_CASH_EXPENSES, INCREASE_IN_CA, INCREASE_IN_CL,
        INTEREST, TAX_RATE, CAPEX,
    ) == pytest.approx(EXPECTED_FCFF, abs=0.1)


def test_fcff_from_nopat(calc):
    assert calc.fcff_from_nopat(
        NOPAT_VALUE, NON_CASH_EXPENSES, INCREASE_IN_CA, INCREASE_IN_CL, CAPEX,
    ) == pytest.approx(EXPECTED_FCFF, abs=0.1)


def test_fcff_from_cfo(calc):
    assert calc.fcff_from_cfo(
        CFO, INTEREST, TAX_RATE, CAPEX,
    ) == pytest.approx(EXPECTED_FCFF, abs=0.1)


def test_fcff_three_methods_agree(calc):
    v1 = calc.fcff_from_net_income(
        NET_INCOME, NON_CASH_EXPENSES, INCREASE_IN_CA, INCREASE_IN_CL,
        INTEREST, TAX_RATE, CAPEX,
    )
    v2 = calc.fcff_from_nopat(
        NOPAT_VALUE, NON_CASH_EXPENSES, INCREASE_IN_CA, INCREASE_IN_CL, CAPEX,
    )
    v3 = calc.fcff_from_cfo(CFO, INTEREST, TAX_RATE, CAPEX)
    assert v1 == pytest.approx(v2, abs=0.01)
    assert v2 == pytest.approx(v3, abs=0.01)
    assert v1 == pytest.approx(v3, abs=0.01)


# --- FCFE ---

def test_fcfe_from_net_income(calc):
    assert calc.fcfe_from_net_income(
        NET_INCOME, NON_CASH_EXPENSES, INCREASE_IN_CA, INCREASE_IN_CL,
        CAPEX, NET_BORROWING,
    ) == pytest.approx(EXPECTED_FCFE, abs=0.1)


def test_fcfe_from_fcff(calc):
    assert calc.fcfe_from_fcff(
        EXPECTED_FCFF, INTEREST, TAX_RATE, NET_BORROWING,
    ) == pytest.approx(EXPECTED_FCFE, abs=0.1)


def test_fcfe_from_ocf(calc):
    assert calc.fcfe_from_ocf(
        OCF, CAPEX, NET_BORROWING,
    ) == pytest.approx(EXPECTED_FCFE, abs=0.1)


def test_fcfe_three_methods_agree(calc):
    fcff = calc.fcff_from_cfo(CFO, INTEREST, TAX_RATE, CAPEX)
    v1 = calc.fcfe_from_net_income(
        NET_INCOME, NON_CASH_EXPENSES, INCREASE_IN_CA, INCREASE_IN_CL,
        CAPEX, NET_BORROWING,
    )
    v2 = calc.fcfe_from_fcff(fcff, INTEREST, TAX_RATE, NET_BORROWING)
    v3 = calc.fcfe_from_ocf(OCF, CAPEX, NET_BORROWING)
    assert v1 == pytest.approx(v2, abs=0.01)
    assert v2 == pytest.approx(v3, abs=0.01)
    assert v1 == pytest.approx(v3, abs=0.01)
