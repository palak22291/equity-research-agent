#!/usr/bin/env python3
"""
Accepts financial data as JSON via stdin, computes validated FCFF and FCFE,
prints results as JSON.

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
  tolerance   -- max allowed spread (in crore) across the 3 FCFF/FCFE methods before
                 cross-validation fails. Default: 2.0 crore. Tighten to 0.1 for
                 exact reference data; loosen further if source data is heavily rounded.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[4]))

from app.calculators.cashflows import CashFlowCalculator

_CRORE = 10_000_000


def _c(value):
    """Convert raw INR to crore. Returns None if value is None."""
    return value / _CRORE if value is not None else None


def main():
    data = json.load(sys.stdin)

    net_income      = _c(data["net_income"])
    non_cash_exp    = _c(data["non_cash_expenses"])
    cfo             = _c(data["cfo"])
    capex           = _c(data["capex"])
    ebit            = _c(data["ebit"])
    interest        = _c(data["interest_expense"])
    tax_expense     = _c(data["tax_expense"])
    pretax_income   = _c(data["pretax_income"])
    delta_ca        = _c(data["increase_in_current_assets"])
    delta_cl        = _c(data["increase_in_current_liabilities"])
    net_borrowing   = _c(data["net_borrowing"])
    tolerance       = data.get("tolerance", 2.0)

    # Tax rate derived from income statement (ratio, so crore/crore = same as raw/raw)
    if pretax_income == 0:
        print(json.dumps({"error": "pretax_income is zero — cannot compute tax rate"}))
        sys.exit(1)
    tax_rate = tax_expense / pretax_income

    calc = CashFlowCalculator()

    try:
        fcff = calc.validated_fcff(
            net_income=net_income,
            non_cash_expenses=non_cash_exp,
            increase_in_current_assets=delta_ca,
            increase_in_current_liabilities=delta_cl,
            interest=interest,
            tax_rate=tax_rate,
            capex=capex,
            cfo=cfo,
            ebit=ebit,
            tolerance=tolerance,
        )
    except ValueError as exc:
        print(json.dumps({"error": f"FCFF cross-validation failed: {exc}"}))
        sys.exit(1)

    try:
        fcfe = calc.validated_fcfe(
            net_income=net_income,
            non_cash_expenses=non_cash_exp,
            increase_in_current_assets=delta_ca,
            increase_in_current_liabilities=delta_cl,
            interest=interest,
            tax_rate=tax_rate,
            capex=capex,
            cfo=cfo,
            ebit=ebit,
            ocf=cfo,
            net_borrowing=net_borrowing,
            tolerance=tolerance,
        )
    except ValueError as exc:
        print(json.dumps({"error": f"FCFE cross-validation failed: {exc}"}))
        sys.exit(1)

    # Individual method values for transparency
    nopat = calc.nopat(ebit, tax_rate)
    after_tax_interest = interest * (1 - tax_rate)

    result = {
        "inputs": {
            "net_income":                    round(net_income, 2),
            "non_cash_expenses":             round(non_cash_exp, 2),
            "cfo":                           round(cfo, 2),
            "capex":                         round(capex, 2),
            "ebit":                          round(ebit, 2),
            "interest_expense":              round(interest, 2),
            "tax_rate":                      round(tax_rate, 6),
            "increase_in_current_assets":    round(delta_ca, 2),
            "increase_in_current_liabilities": round(delta_cl, 2),
            "net_borrowing":                 round(net_borrowing, 2),
        },
        "derived": {
            "nopat":              round(nopat, 2),
            "after_tax_interest": round(after_tax_interest, 2),
        },
        "fcff": {
            "method_1_net_income": round(calc.fcff_from_net_income(
                net_income, non_cash_exp, delta_ca, delta_cl, interest, tax_rate, capex
            ), 2),
            "method_2_nopat": round(calc.fcff_from_nopat(
                nopat, non_cash_exp, delta_ca, delta_cl, capex
            ), 2),
            "method_3_cfo": round(calc.fcff_from_cfo(cfo, interest, tax_rate, capex), 2),
            "validated_fcff": fcff,
        },
        "fcfe": {
            "method_1_net_income": round(calc.fcfe_from_net_income(
                net_income, non_cash_exp, delta_ca, delta_cl, capex, net_borrowing
            ), 2),
            "method_2_fcff": round(calc.fcfe_from_fcff(fcff, interest, tax_rate, net_borrowing), 2),
            "method_3_ocf": round(calc.fcfe_from_ocf(cfo, capex, net_borrowing), 2),
            "validated_fcfe": fcfe,
        },
        "cross_validation": "passed",
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
