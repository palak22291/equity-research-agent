#!/usr/bin/env python3
"""
Accepts financial + market inputs as JSON via stdin, computes WACC components,
prints results as JSON.

Required input keys:
  interest_expense    -- raw INR (from get_financial_statements)
  book_value_debt     -- raw INR; typically total_non_current_liabilities
  book_value_equity   -- raw INR; shareholders_equity
  tax_expense         -- raw INR (from get_financial_statements)
  pretax_income       -- raw INR (from get_financial_statements)
  risk_free_rate      -- decimal (e.g. 0.0685 for 10-year Indian G-sec yield)
  beta                -- from get_market_data
  market_return       -- decimal (e.g. 0.12 for long-run Nifty 50 return)

Optional input keys:
  historical_weights  -- list of {book_value_debt, book_value_equity} dicts, one per year,
                         all in raw INR. When provided, Wd and We are computed as the
                         median across all years rather than from the single current year.
                         Use this for multi-year WACC to reduce point-in-time distortion.
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[4]))

from app.calculators.cost_of_capital import CostOfCapitalCalculator

_CRORE = 10_000_000


def _c(value):
    return value / _CRORE if value is not None else None


def main():
    data = json.load(sys.stdin)

    interest_expense  = _c(data["interest_expense"])
    book_value_debt   = _c(data["book_value_debt"])
    book_value_equity = _c(data["book_value_equity"])
    tax_expense       = _c(data["tax_expense"])
    pretax_income     = _c(data["pretax_income"])
    risk_free_rate    = data["risk_free_rate"]
    beta              = data["beta"]
    market_return     = data["market_return"]
    historical_weights = data.get("historical_weights")

    if pretax_income == 0:
        print(json.dumps({"error": "pretax_income is zero — cannot compute tax rate"}))
        sys.exit(1)
    if book_value_debt == 0:
        print(json.dumps({"error": "book_value_debt is zero — cannot compute pre-tax cost of debt"}))
        sys.exit(1)

    tax_rate = tax_expense / pretax_income
    pre_tax_kd = interest_expense / book_value_debt

    calc = CostOfCapitalCalculator()

    ke = calc.capm_cost_of_equity(risk_free_rate, beta, market_return)
    kd = calc.post_tax_cost_of_debt(pre_tax_kd, tax_rate)

    # Weights: median across historical years if provided, else current year only
    if historical_weights:
        wd_series = [
            calc.weight_of_debt(_c(y["book_value_debt"]), _c(y["book_value_equity"]))
            for y in historical_weights
        ]
        we_series = [
            calc.weight_of_equity(_c(y["book_value_debt"]), _c(y["book_value_equity"]))
            for y in historical_weights
        ]
        wd = statistics.median(wd_series)
        we = statistics.median(we_series)
    else:
        wd = calc.weight_of_debt(book_value_debt, book_value_equity)
        we = calc.weight_of_equity(book_value_debt, book_value_equity)

    wacc = calc.wacc(wd, kd, we, ke)

    result = {
        "inputs": {
            "interest_expense":   round(interest_expense, 2),
            "book_value_debt":    round(book_value_debt, 2),
            "book_value_equity":  round(book_value_equity, 2),
            "tax_rate":           round(tax_rate, 6),
            "pre_tax_kd":         round(pre_tax_kd, 6),
            "risk_free_rate":     risk_free_rate,
            "beta":               beta,
            "market_return":      market_return,
            "weights_source":     "median across historical years" if historical_weights else "current year only",
        },
        "capm_breakdown": {
            "formula":      "Ke = Rf + Beta × (Rm - Rf)",
            "rf":           risk_free_rate,
            "beta":         beta,
            "rm":           market_return,
            "equity_risk_premium": round(market_return - risk_free_rate, 6),
            "ke":           ke,
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
            "wd_x_kd": round(wd * kd, 6),
            "we_x_ke": round(we * ke, 6),
            "wacc":    wacc,
        },
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
