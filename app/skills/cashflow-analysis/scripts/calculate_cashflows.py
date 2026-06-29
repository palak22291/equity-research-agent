#!/usr/bin/env python3
"""
Accepts financial data as JSON via stdin, computes FCFF and FCFE via 3 independent
methods each, and prints results as JSON.

Output schema matches the run_cashflow_analysis tool contract consumed by the
valuation agent (which reads fcff.validated_fcff and fcfe.validated_fcfe).

Cross-validation never crashes. When methods disagree beyond tolerance the
validated value is the average of the two closest methods, and a data_quality_note
is added to that section.

Required input keys (all monetary values in raw INR as returned by yfinance provider):
  net_income, non_cash_expenses, cfo, capex, ebit, interest_expense,
  tax_expense, pretax_income,
  increase_in_current_assets, increase_in_current_liabilities, net_borrowing

Optional input keys:
  tolerance   -- spread (in crore) that triggers a data_quality_note. Default 500.0.
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


def _best_estimate(v1: float, v2: float, v3: float):
    """Return (best_estimate, spread). Best estimate is the average of the two
    methods closest to each other; spread is max - min across all three."""
    pairs = [(abs(v1 - v2), v1, v2), (abs(v1 - v3), v1, v3), (abs(v2 - v3), v2, v3)]
    _, a, b = min(pairs, key=lambda x: x[0])
    spread = round(max(v1, v2, v3) - min(v1, v2, v3), 2)
    return round((a + b) / 2, 2), spread


def main():
    data = json.load(sys.stdin)

    try:
        ni      = _c(data["net_income"])
        nce     = _c(data["non_cash_expenses"])
        cfo_c   = _c(data["cfo"])
        capex_c = _c(data["capex"])
        eb      = _c(data["ebit"])
        ie      = _c(data["interest_expense"])
        te      = _c(data["tax_expense"])
        pi      = _c(data["pretax_income"])
        dca     = _c(data["increase_in_current_assets"])
        dcl     = _c(data["increase_in_current_liabilities"])
        nb      = _c(data["net_borrowing"])
        tolerance = data.get("tolerance", 500.0)

        if pi == 0:
            print(json.dumps({"error": "pretax_income is zero — cannot compute tax rate"}))
            return
        tax_rate = te / pi

        calc = CashFlowCalculator()
        nopat = calc.nopat(eb, tax_rate)

        # --- FCFF: 3 independent methods, then a robust best estimate ---
        fcff_m1 = round(calc.fcff_from_net_income(ni, nce, dca, dcl, ie, tax_rate, capex_c), 2)
        fcff_m2 = round(calc.fcff_from_nopat(nopat, nce, dca, dcl, capex_c), 2)
        fcff_m3 = round(calc.fcff_from_cfo(cfo_c, ie, tax_rate, capex_c), 2)
        fcff_best, fcff_spread = _best_estimate(fcff_m1, fcff_m2, fcff_m3)

        # --- FCFE: method 2 feeds off fcff_best to avoid propagating FCFF spread ---
        fcfe_m1 = round(calc.fcfe_from_net_income(ni, nce, dca, dcl, capex_c, nb), 2)
        fcfe_m2 = round(calc.fcfe_from_fcff(fcff_best, ie, tax_rate, nb), 2)
        fcfe_m3 = round(calc.fcfe_from_ocf(cfo_c, capex_c, nb), 2)
        fcfe_best, fcfe_spread = _best_estimate(fcfe_m1, fcfe_m2, fcfe_m3)

        within_tol = fcff_spread <= tolerance and fcfe_spread <= tolerance
        cross_validation = "passed" if within_tol else "approximate"

        fcff_block = {
            "method_1_net_income": fcff_m1,
            "method_2_nopat":      fcff_m2,
            "method_3_cfo":        fcff_m3,
            "spread":              fcff_spread,
            "validated_fcff":      fcff_best,
        }
        fcfe_block = {
            "method_1_net_income": fcfe_m1,
            "method_2_fcff":       fcfe_m2,
            "method_3_ocf":        fcfe_m3,
            "spread":              fcfe_spread,
            "validated_fcfe":      fcfe_best,
        }
        if fcff_spread > tolerance:
            fcff_block["data_quality_note"] = (
                f"FCFF methods differ by {fcff_spread} crore (tolerance {tolerance}). "
                f"validated_fcff is the average of the two closest methods."
            )
        if fcfe_spread > tolerance:
            fcfe_block["data_quality_note"] = (
                f"FCFE methods differ by {fcfe_spread} crore (tolerance {tolerance}). "
                f"validated_fcfe is the average of the two closest methods."
            )

        print(json.dumps({
            "tool": "run_cashflow_analysis",
            "inputs": {
                "net_income":                      round(ni, 2),
                "non_cash_expenses":               round(nce, 2),
                "cfo":                             round(cfo_c, 2),
                "capex":                           round(capex_c, 2),
                "tax_rate":                        round(tax_rate, 6),
                "increase_in_current_assets":      round(dca, 2),
                "increase_in_current_liabilities": round(dcl, 2),
                "net_borrowing":                   round(nb, 2),
            },
            "fcff": fcff_block,
            "fcfe": fcfe_block,
            "cross_validation": cross_validation,
        }, indent=2))

    except Exception as exc:
        print(json.dumps({"error": f"Cashflow analysis failed: {exc}"}))


if __name__ == "__main__":
    main()
