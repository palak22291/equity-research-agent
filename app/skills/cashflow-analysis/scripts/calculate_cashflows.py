#!/usr/bin/env python3
"""
Accepts financial data as JSON via stdin, computes FCFF and FCFE via 3 independent
methods each, and prints results as JSON.

Cross-validation never crashes. When methods disagree beyond tolerance:
  - best_estimate_fcff / best_estimate_fcfe: average of the two closest methods
  - cross_validation_warning: message describing the disagreement
  - large_spread_warning: true when spread > 50 crore (regardless of tolerance)

Required input keys (all monetary values in raw INR as returned by yfinance provider):
  net_income, non_cash_expenses, cfo, capex, ebit, interest_expense,
  tax_expense, pretax_income,
  increase_in_current_assets    -- ΔCA: current year CA minus prior year CA (raw INR)
  increase_in_current_liabilities -- ΔCL: current year CL minus prior year CL (raw INR)
  net_borrowing                 -- new long-term debt minus repaid debt (raw INR;
                                   positive = net new borrowing, negative = net repayment)

These delta values require two years of balance sheet data. The agent must gather
prior-year data from get_financial_statements before calling this script.

Optional input keys:
  tolerance   -- spread (in crore) that triggers cross_validation_warning.
                 Default: 500.0 crore. Use 0.1 for exact reference data.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[4]))

from app.calculators.cashflows import CashFlowCalculator

_CRORE = 10_000_000
_LARGE_SPREAD_THRESHOLD = 50.0


def _c(value):
    """Convert raw INR to crore. Returns None if value is None."""
    return value / _CRORE if value is not None else None


def _best_estimate(v1: float, v2: float, v3: float) -> float:
    """Return the average of the two methods closest to each other."""
    pairs = [(abs(v1 - v2), v1, v2), (abs(v1 - v3), v1, v3), (abs(v2 - v3), v2, v3)]
    _, a, b = min(pairs, key=lambda x: x[0])
    return round((a + b) / 2, 2)


def _cv_section(label: str, v1: float, v2: float, v3: float, tolerance: float) -> dict:
    """Build cross-validation metadata for one set of 3 method values."""
    spread = round(max(v1, v2, v3) - min(v1, v2, v3), 2)
    best = _best_estimate(v1, v2, v3)
    section = {
        "spread": spread,
        f"best_estimate_{label}": best,
        "cross_validation": "passed" if spread <= tolerance else "warning",
    }
    if spread > tolerance:
        section["cross_validation_warning"] = (
            f"{label.upper()} methods disagree by {spread:.2f} crore "
            f"(tolerance {tolerance} crore). Methods: {v1}, {v2}, {v3}. "
            "Using average of two closest methods as best estimate."
        )
    if spread > _LARGE_SPREAD_THRESHOLD:
        section["large_spread_warning"] = True
    return section


def main():
    data = json.load(sys.stdin)

    net_income    = _c(data["net_income"])
    non_cash_exp  = _c(data["non_cash_expenses"])
    cfo           = _c(data["cfo"])
    capex         = _c(data["capex"])
    ebit          = _c(data["ebit"])
    interest      = _c(data["interest_expense"])
    tax_expense   = _c(data["tax_expense"])
    pretax_income = _c(data["pretax_income"])
    delta_ca      = _c(data["increase_in_current_assets"])
    delta_cl      = _c(data["increase_in_current_liabilities"])
    net_borrowing = _c(data["net_borrowing"])
    tolerance     = data.get("tolerance", 500.0)

    # Tax rate derived from income statement (ratio, so crore/crore = same as raw/raw)
    if pretax_income == 0:
        print(json.dumps({"error": "pretax_income is zero — cannot compute tax rate"}))
        sys.exit(1)
    tax_rate = tax_expense / pretax_income

    calc = CashFlowCalculator()
    nopat = calc.nopat(ebit, tax_rate)
    after_tax_interest = interest * (1 - tax_rate)

    # --- FCFF: compute all 3 methods independently ---
    fcff_m1 = round(calc.fcff_from_net_income(
        net_income, non_cash_exp, delta_ca, delta_cl, interest, tax_rate, capex
    ), 2)
    fcff_m2 = round(calc.fcff_from_nopat(nopat, non_cash_exp, delta_ca, delta_cl, capex), 2)
    fcff_m3 = round(calc.fcff_from_cfo(cfo, interest, tax_rate, capex), 2)

    fcff_cv = _cv_section("fcff", fcff_m1, fcff_m2, fcff_m3, tolerance)
    best_fcff = fcff_cv["best_estimate_fcff"]

    # --- FCFE: method 2 feeds best_estimate_fcff to avoid propagating FCFF spread ---
    fcfe_m1 = round(calc.fcfe_from_net_income(
        net_income, non_cash_exp, delta_ca, delta_cl, capex, net_borrowing
    ), 2)
    fcfe_m2 = round(calc.fcfe_from_fcff(best_fcff, interest, tax_rate, net_borrowing), 2)
    fcfe_m3 = round(calc.fcfe_from_ocf(cfo, capex, net_borrowing), 2)

    fcfe_cv = _cv_section("fcfe", fcfe_m1, fcfe_m2, fcfe_m3, tolerance)

    overall_status = (
        "passed"
        if fcff_cv["cross_validation"] == "passed" and fcfe_cv["cross_validation"] == "passed"
        else "warning"
    )

    result = {
        "inputs": {
            "net_income":                      round(net_income, 2),
            "non_cash_expenses":               round(non_cash_exp, 2),
            "cfo":                             round(cfo, 2),
            "capex":                           round(capex, 2),
            "ebit":                            round(ebit, 2),
            "interest_expense":                round(interest, 2),
            "tax_rate":                        round(tax_rate, 6),
            "increase_in_current_assets":      round(delta_ca, 2),
            "increase_in_current_liabilities": round(delta_cl, 2),
            "net_borrowing":                   round(net_borrowing, 2),
        },
        "derived": {
            "nopat":              round(nopat, 2),
            "after_tax_interest": round(after_tax_interest, 2),
        },
        "fcff": {
            "method_1_net_income": fcff_m1,
            "method_2_nopat":      fcff_m2,
            "method_3_cfo":        fcff_m3,
            **fcff_cv,
        },
        "fcfe": {
            "method_1_net_income": fcfe_m1,
            "method_2_fcff":       fcfe_m2,
            "method_3_ocf":        fcfe_m3,
            **fcfe_cv,
        },
        "cross_validation": overall_status,
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
