#!/usr/bin/env python3
"""
Accepts financial data as JSON via stdin, computes all ratios, prints results as JSON.

Required input keys (all monetary values in raw INR as returned by yfinance provider):
  current_assets, current_liabilities, cash, accounts_receivable, inventory,
  total_assets, total_non_current_liabilities, shareholders_equity,
  total_revenue, gross_profit, net_income, ebit, interest_expense

Optional input keys:
  non_cash_expenses       -- raw INR; enables ebitda_margin
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

    current_assets      = _c(data["current_assets"])
    current_liabilities = _c(data["current_liabilities"])
    cash                = _c(data["cash"])
    accounts_receivable = _c(data["accounts_receivable"])
    inventory           = _c(data["inventory"])
    total_assets        = _c(data["total_assets"])
    long_term_debt      = _c(data["total_non_current_liabilities"])
    shareholders_equity = _c(data["shareholders_equity"])
    total_revenue       = _c(data["total_revenue"])
    gross_profit        = _c(data["gross_profit"])
    net_income          = _c(data["net_income"])
    ebit                = _c(data["ebit"])
    interest_expense    = _c(data["interest_expense"])
    non_cash_expenses   = _c(data.get("non_cash_expenses"))

    # Market data (already correct units from provider)
    current_price      = data.get("current_price")       # INR per share, no conversion
    shares_outstanding = data.get("shares_outstanding")  # crore

    # Derived quantities
    cogs         = total_revenue - gross_profit
    fixed_assets = total_assets - current_assets
    # For ROCE: all liabilities = total capital minus equity
    total_liabilities = current_liabilities + long_term_debt

    c = RatioCalculator()

    npm = c.net_profit_margin(net_income, total_revenue)
    at  = c.asset_turnover(total_revenue, total_assets)
    em  = round(total_assets / shareholders_equity, 6) if shareholders_equity else None

    result = {
        "liquidity": {
            "current_ratio": c.current_ratio(current_assets, current_liabilities),
            "quick_ratio":   c.quick_ratio(cash, accounts_receivable, current_liabilities),
            "cash_ratio":    c.cash_ratio(cash, current_liabilities),
        },
        "solvency": {
            "debt_to_equity":    c.debt_to_equity(current_liabilities, long_term_debt, shareholders_equity),
            "interest_coverage": c.interest_coverage(ebit, interest_expense),
            "debt_to_assets":    c.debt_to_assets(total_liabilities, total_assets),
        },
        "profitability": {
            "gross_profit_margin": c.gross_profit_margin(gross_profit, total_revenue),
            "ebit_margin":         c.ebit_margin(ebit, total_revenue),
            "ebitda_margin":       (
                c.ebitda_margin(ebit + non_cash_expenses, total_revenue)
                if non_cash_expenses is not None else None
            ),
            "net_profit_margin":   npm,
            "return_on_equity":    c.return_on_equity(net_income, shareholders_equity),
            "return_on_assets":    c.return_on_assets(net_income, total_assets),
            "roce":                c.roce(ebit, shareholders_equity, total_liabilities),
        },
        "efficiency": {
            "asset_turnover":         at,
            "inventory_turnover":     c.inventory_turnover(cogs, inventory),
            "receivables_turnover":   c.receivables_turnover(total_revenue, accounts_receivable),
            "fixed_asset_turnover":   c.fixed_asset_turnover(total_revenue, fixed_assets),
            "days_sales_outstanding": c.days_sales_outstanding(accounts_receivable, total_revenue),
        },
        "dupont": {
            "net_profit_margin": npm,
            "asset_turnover":    at,
            "equity_multiplier": round(em, 2) if em is not None else None,
            "roe":               c.dupont_roe(npm, at, em) if em is not None else None,
        },
    }

    if current_price is not None and shares_outstanding is not None:
        eps_val = c.eps(net_income, shares_outstanding)
        result["valuation"] = {
            "eps":      eps_val,
            "pe_ratio": c.pe_ratio(current_price, eps_val),
        }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
