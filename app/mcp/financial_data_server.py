"""
FastMCP server exposing financial data tools backed by YFinanceProvider.

Run with:
    python -m app.mcp.financial_data_server
or via MCP client configuration pointing to this module.
"""

import os

import yfinance as yf
from fastmcp import FastMCP

from app.mcp.providers.yfinance_provider import YFinanceProvider

mcp = FastMCP("equity-research-financial-data")
_provider = YFinanceProvider()

_INDIAN_SUFFIXES = {".NS", ".BO"}


def _ensure_ns_suffix(ticker: str) -> str:
    upper = ticker.upper()
    if any(upper.endswith(s) for s in _INDIAN_SUFFIXES):
        return ticker
    return ticker + ".NS"


def _r2(value):
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _get_col(df, col_index, *labels):
    for label in labels:
        if label in df.index and df.shape[1] > col_index:
            try:
                return float(df.loc[label].iloc[col_index])
            except (TypeError, ValueError):
                pass
    return None


@mcp.tool()
def get_financial_statements(ticker: str) -> dict:
    """
    Fetch the most recent fiscal-year income statement, balance sheet,
    and cash flow data for a company.

    Args:
        ticker: Stock ticker symbol (e.g. "CIPLA", "RELIANCE", "CIPLA.NS").
                Indian stocks without an exchange suffix get .NS appended automatically.

    Returns:
        Dict with keys: ticker, company_name, fiscal_year_end, currency,
        total_assets, current_assets, inventory, cash, accounts_receivable,
        current_liabilities, total_non_current_liabilities, shareholders_equity,
        total_revenue, gross_profit, net_income, ebit, interest_expense,
        tax_expense, pretax_income, cfo, capex, non_cash_expenses.
        On failure, returns {"error": "<message>", "ticker": "<ticker>"}.
    """
    return _provider.get_financial_statements(ticker)


@mcp.tool()
def get_market_data(ticker: str) -> dict:
    """
    Fetch current market data for a company.

    Args:
        ticker: Stock ticker symbol. Indian stocks get .NS appended if no suffix present.

    Returns:
        Dict with keys: ticker, company_name, current_price, shares_outstanding
        (in crore), beta, market_cap, currency.
        On failure, returns {"error": "<message>", "ticker": "<ticker>"}.
    """
    return _provider.get_market_data(ticker)


@mcp.tool()
def get_sector_growth_rate(ticker: str, sector: str) -> dict:
    """
    Return the expected long-run nominal growth rate for a sector.

    Supported sectors: pharmaceuticals, it, banking, fmcg, automobiles,
    oil_gas, telecom, metals, cement, power, healthcare.
    Unknown sectors fall back to the default rate (0.08).

    Args:
        ticker: Stock ticker (included in the response for traceability).
        sector: Sector name (case-insensitive, spaces and slashes normalised).

    Returns:
        Dict with keys: ticker, sector, growth_rate.
    """
    rate = _provider.get_sector_growth_rate(sector)
    return {"ticker": ticker, "sector": sector, "growth_rate": rate}


@mcp.tool()
def fetch_all_financial_data(ticker: str, sector: str, beta_override: float = 0.0) -> dict:
    """Fetch complete financial data for a company in a single call: income
    statement, balance sheet, cash flow statement, market data, sector growth
    rate, and year-over-year balance-sheet deltas needed for free cash flow
    calculations.

    Args:
        ticker: Stock ticker symbol (e.g. "CIPLA", "INFY", "RELIANCE").
                Indian stocks without an exchange suffix get .NS appended automatically.
        sector: Business sector (e.g. "pharmaceuticals", "it", "banking", "fmcg",
                "automobiles", "telecom", "metals", "cement", "power", "healthcare").
        beta_override: If > 0, use this value instead of the yfinance beta.
                       Useful when the analyst has a custom beta estimate.

    Returns:
        Dict with all financial fields needed for ratio analysis, cashflow
        analysis, WACC computation, and DCF valuation. All monetary values are
        raw INR (as returned by yfinance). shares_outstanding is in crore.
        growth_rate is a decimal. On error, returns a dict with an "error" key.
    """
    # --- Financial statements (current year) ---
    statements = _provider.get_financial_statements(ticker)
    if "error" in statements:
        return statements

    # --- Market data ---
    market = _provider.get_market_data(ticker)
    if "error" in market:
        return market

    # --- Sector growth rate ---
    growth_rate = _provider.get_sector_growth_rate(sector)

    # --- Balance sheet deltas (current vs prior year) ---
    ns_ticker = _ensure_ns_suffix(ticker)
    delta_ca = delta_cl = net_borrowing = None
    try:
        stock = yf.Ticker(ns_ticker)
        balance = stock.balance_sheet
        if balance is not None and not balance.empty and balance.shape[1] >= 2:
            curr_ca = _get_col(balance, 0, "Current Assets")
            prev_ca = _get_col(balance, 1, "Current Assets")
            curr_cl = _get_col(balance, 0, "Current Liabilities")
            prev_cl = _get_col(balance, 1, "Current Liabilities")
            curr_ltd = _get_col(balance, 0,
                                "Total Non Current Liabilities Net Minority Interest",
                                "Long Term Debt")
            prev_ltd = _get_col(balance, 1,
                                "Total Non Current Liabilities Net Minority Interest",
                                "Long Term Debt")
            if curr_ca is not None and prev_ca is not None:
                delta_ca = _r2(curr_ca - prev_ca)
            if curr_cl is not None and prev_cl is not None:
                delta_cl = _r2(curr_cl - prev_cl)
            if curr_ltd is not None and prev_ltd is not None:
                net_borrowing = _r2(curr_ltd - prev_ltd)
    except Exception as exc:
        print(f"[mcp] WARNING: balance sheet delta fetch failed: {exc}")

    result = {
        # metadata
        "ticker": statements["ticker"],
        "company_name": statements["company_name"],
        "fiscal_year_end": statements["fiscal_year_end"],
        "currency": statements["currency"],
        "sector": sector,
        "growth_rate": growth_rate,
        # balance sheet (raw INR)
        "total_assets": statements["total_assets"],
        "current_assets": statements["current_assets"],
        "inventory": statements["inventory"],
        "cash": statements["cash"],
        "accounts_receivable": statements["accounts_receivable"],
        "current_liabilities": statements["current_liabilities"],
        "total_non_current_liabilities": statements["total_non_current_liabilities"],
        "shareholders_equity": statements["shareholders_equity"],
        # income statement (raw INR)
        "total_revenue": statements["total_revenue"],
        "gross_profit": statements["gross_profit"],
        "net_income": statements["net_income"],
        "ebit": statements["ebit"],
        "interest_expense": statements["interest_expense"],
        "tax_expense": statements["tax_expense"],
        "pretax_income": statements["pretax_income"],
        # cash flow (raw INR)
        "cfo": statements["cfo"],
        "capex": statements["capex"],
        "non_cash_expenses": statements["non_cash_expenses"],
        # market data
        "current_price": market["current_price"],
        "shares_outstanding": market["shares_outstanding"],
        "beta": beta_override if beta_override > 0 else market["beta"],
        "beta_source": "user_provided" if beta_override > 0 else "yfinance",
        "market_cap": market["market_cap"],
        # year-over-year balance sheet deltas (raw INR)
        **({"beta_override_note": f"yfinance beta ({_r2(market['beta'])}) replaced by analyst-provided beta ({beta_override})"} if beta_override > 0 else {}),
        "increase_in_current_assets": delta_ca,
        "increase_in_current_liabilities": delta_cl,
        "net_borrowing": net_borrowing,
        # market assumptions (India defaults; override via env if needed)
        "risk_free_rate": float(os.environ.get("RISK_FREE_RATE", "0.0685")),
        "market_return": float(os.environ.get("MARKET_RETURN", "0.12")),
    }
    return result


if __name__ == "__main__":
    mcp.run()
