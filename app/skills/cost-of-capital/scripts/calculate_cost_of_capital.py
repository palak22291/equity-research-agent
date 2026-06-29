#!/usr/bin/env python3
"""
Accepts financial + market inputs as JSON via stdin, computes WACC components,
prints results as JSON.

Output schema matches the calculate_cost_of_capital tool contract consumed by the
valuation agent (which reads the top-level "ke" and "wacc" fields) and the report
agent (which reads the capm_breakdown / cost_of_debt / weights / wacc blocks).

Required input keys:
  interest_expense              -- raw INR (from get_financial_statements)
  total_non_current_liabilities -- raw INR; book value of debt
  shareholders_equity           -- raw INR; book value of equity
  tax_expense                   -- raw INR (from get_financial_statements)
  pretax_income                 -- raw INR (from get_financial_statements)
  risk_free_rate                -- decimal (e.g. 0.0685 for 10-year Indian G-sec yield)
  beta                          -- from get_market_data
  market_return                 -- decimal (e.g. 0.12 for long-run Nifty 50 return)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[4]))

from app.calculators.cost_of_capital import CostOfCapitalCalculator

_CRORE = 10_000_000


def _c(value):
    return value / _CRORE if value is not None else None


def main():
    data = json.load(sys.stdin)

    try:
        ie  = _c(data["interest_expense"])
        ltd = _c(data["total_non_current_liabilities"])
        eq  = _c(data["shareholders_equity"])
        te  = _c(data["tax_expense"])
        pi  = _c(data["pretax_income"])
        risk_free_rate = data["risk_free_rate"]
        beta           = data["beta"]
        market_return  = data["market_return"]

        if pi == 0:
            print(json.dumps({"error": "pretax_income is zero — cannot compute tax rate"}))
            return
        if not ltd or ltd == 0:
            print(json.dumps({"error": "total_non_current_liabilities is zero — cannot compute cost of debt"}))
            return

        tax_rate   = te / pi
        pre_tax_kd = ie / ltd

        calc = CostOfCapitalCalculator()

        ke   = calc.capm_cost_of_equity(risk_free_rate, beta, market_return)
        kd   = calc.post_tax_cost_of_debt(pre_tax_kd, tax_rate)
        wd   = calc.weight_of_debt(ltd, eq)
        we   = calc.weight_of_equity(ltd, eq)
        wacc = calc.wacc(wd, kd, we, ke)

        print(json.dumps({
            "tool": "calculate_cost_of_capital",
            "capm_breakdown": {
                "formula":             "Ke = Rf + Beta × (Rm - Rf)",
                "risk_free_rate":      risk_free_rate,
                "beta":                beta,
                "market_return":       market_return,
                "equity_risk_premium": round(market_return - risk_free_rate, 6),
                "ke":                  ke,
            },
            "cost_of_debt": {
                "pre_tax_kd":  round(pre_tax_kd, 6),
                "tax_rate":    round(tax_rate, 6),
                "post_tax_kd": kd,
            },
            "weights": {
                "wd": round(wd, 6),
                "we": round(we, 6),
            },
            "wacc": {
                "formula": "WACC = (Wd × Kd) + (We × Ke)",
                "wacc":    wacc,
            },
            "ke":   ke,
            "kd":   kd,
            "wacc": wacc,
        }, indent=2))

    except Exception as exc:
        print(json.dumps({"error": f"Cost of capital calculation failed: {exc}"}))


if __name__ == "__main__":
    main()
