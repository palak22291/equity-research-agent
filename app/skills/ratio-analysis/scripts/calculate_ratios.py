#!/usr/bin/env python3
"""
Accepts financial data as JSON via stdin, computes all ratios, prints results as JSON.

Output schema matches the run_ratio_analysis tool contract consumed by the
analysis/report agents (includes the `financials_crore` block the report agent
quotes for absolute monetary figures).

Required input keys (all monetary values in raw INR as returned by yfinance provider):
  total_assets, current_assets, inventory, cash, accounts_receivable,
  current_liabilities, total_non_current_liabilities, shareholders_equity,
  total_revenue, gross_profit, net_income, ebit, interest_expense

Optional input keys:
  current_price           -- price per share (no conversion needed)
  shares_outstanding      -- already in crore (as returned by get_market_data)
"""
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path when script is invoked directly.
sys.path.insert(0, str(Path(__file__).parents[4]))

from app.calculators.ratios import RatioCalculator

_CRORE = 10_000_000


def _c(value):
    """Convert raw INR to crore. Returns None if value is None."""
    return value / _CRORE if value is not None else None


def main():
    data = json.load(sys.stdin)

    try:
        ca  = _c(data["current_assets"])
        cl  = _c(data["current_liabilities"])
        ch  = _c(data["cash"])
        ar  = _c(data["accounts_receivable"])
        inv = _c(data["inventory"])
        ta  = _c(data["total_assets"])
        ltd = _c(data["total_non_current_liabilities"])
        eq  = _c(data["shareholders_equity"])
        rev = _c(data["total_revenue"])
        gp  = _c(data["gross_profit"])
        ni  = _c(data["net_income"])
        eb  = _c(data["ebit"])
        ie  = _c(data["interest_expense"])

        current_price      = data.get("current_price")       # INR per share, no conversion
        shares_outstanding = data.get("shares_outstanding")  # crore

        cogs         = rev - gp
        fixed_assets = ta - ca
        total_liab   = cl + ltd

        r = RatioCalculator()

        npm = r.net_profit_margin(ni, rev)
        at  = r.asset_turnover(rev, ta)
        em  = round(ta / eq, 6) if eq else None

        result = {
            "tool": "run_ratio_analysis",
            # Absolute figures already converted to INR crore by _c() — the report
            # agent must quote these (never the raw-INR values in financial_data).
            "financials_crore": {
                "total_revenue":        round(rev, 2),
                "gross_profit":         round(gp, 2),
                "net_income":           round(ni, 2),
                "ebit":                 round(eb, 2),
                "total_assets":         round(ta, 2),
                "current_assets":       round(ca, 2),
                "current_liabilities":  round(cl, 2),
                "shareholders_equity":  round(eq, 2),
                "cash":                 round(ch, 2),
            },
            "liquidity": {
                "current_ratio": r.current_ratio(ca, cl),
                "quick_ratio":   r.quick_ratio(ch, ar, cl),
                "cash_ratio":    r.cash_ratio(ch, cl),
            },
            "solvency": {
                "debt_to_equity":    r.debt_to_equity(cl, ltd, eq),
                "interest_coverage": r.interest_coverage(eb, ie),
                "debt_to_assets":    r.debt_to_assets(total_liab, ta),
            },
            "profitability": {
                "gross_profit_margin": r.gross_profit_margin(gp, rev),
                "ebit_margin":         r.ebit_margin(eb, rev),
                "net_profit_margin":   npm,
                "return_on_equity":    r.return_on_equity(ni, eq),
                "return_on_assets":    r.return_on_assets(ni, ta),
                "roce":                r.roce(eb, eq, total_liab),
            },
            "efficiency": {
                "asset_turnover":         at,
                "inventory_turnover":     r.inventory_turnover(cogs, inv),
                "receivables_turnover":   r.receivables_turnover(rev, ar),
                "fixed_asset_turnover":   r.fixed_asset_turnover(rev, fixed_assets),
                "days_sales_outstanding": r.days_sales_outstanding(ar, rev),
            },
            "dupont": {
                "net_profit_margin": npm,
                "asset_turnover":    at,
                "equity_multiplier": round(em, 2) if em is not None else None,
                "roe":               r.dupont_roe(npm, at, em) if em is not None else None,
            },
        }

        if current_price is not None and shares_outstanding is not None:
            eps_val = r.eps(ni, shares_outstanding)
            result["valuation_multiples"] = {
                "eps":      eps_val,
                "pe_ratio": r.pe_ratio(current_price, eps_val),
            }

        print(json.dumps(result, indent=2))

    except Exception as exc:
        print(json.dumps({"error": f"Ratio analysis failed: {exc}"}))


if __name__ == "__main__":
    main()
