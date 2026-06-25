"""Data agent — fetches all financial data for a given ticker and sector."""
import json
import os

import yfinance as yf
from google.adk.agents import LlmAgent

from app.mcp.providers.yfinance_provider import YFinanceProvider

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


def _get(df, *labels):
    for label in labels:
        if label in df.index:
            try:
                return float(df.loc[label].iloc[0])
            except (TypeError, ValueError):
                pass
    return None


def _get_col(df, col_index, *labels):
    for label in labels:
        if label in df.index and df.shape[1] > col_index:
            try:
                return float(df.loc[label].iloc[col_index])
            except (TypeError, ValueError):
                pass
    return None


def fetch_all_financial_data(ticker: str, sector: str) -> str:
    """Fetch complete financial data for a company: income statement, balance sheet,
    cash flow statement, market data, sector growth rate, and year-over-year
    balance sheet deltas needed for free cash flow calculations.

    Args:
        ticker: Stock ticker symbol (e.g. "CIPLA", "INFY", "RELIANCE").
                Indian stocks without an exchange suffix get .NS appended automatically.
        sector: Business sector (e.g. "pharmaceuticals", "it", "banking", "fmcg",
                "automobiles", "telecom", "metals", "cement", "power", "healthcare").

    Returns:
        JSON string with all financial fields needed for ratio analysis,
        cashflow analysis, WACC computation, and DCF valuation.
        All monetary values are raw INR (as returned by yfinance).
        shares_outstanding is in crore.
        growth_rate is a decimal.
        On error, returns JSON with an "error" key.
    """
    # --- Financial statements (current year) ---
    statements = _provider.get_financial_statements(ticker)
    if "error" in statements:
        return json.dumps(statements)

    # --- Market data ---
    market = _provider.get_market_data(ticker)
    if "error" in market:
        return json.dumps(market)

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
    except Exception:
        pass  # deltas stay None; cashflow analysis will report missing fields

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
        "beta": market["beta"],
        "market_cap": market["market_cap"],
        # year-over-year balance sheet deltas (raw INR)
        "increase_in_current_assets": delta_ca,
        "increase_in_current_liabilities": delta_cl,
        "net_borrowing": net_borrowing,
        # market assumptions (India defaults; override via env if needed)
        "risk_free_rate": float(os.environ.get("RISK_FREE_RATE", "0.0685")),
        "market_return": float(os.environ.get("MARKET_RETURN", "0.12")),
    }
    return json.dumps(result)


data_agent = LlmAgent(
    name="data_agent",
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    instruction="""You are a financial data agent. Given a stock ticker and sector, \
fetch the company's financial statements, market data, and sector growth rate using \
the available tools. Return all data in a structured format.

Call fetch_all_financial_data(ticker, sector) with the ticker and sector provided by \
the user. Output the raw JSON result exactly as returned by the tool — do not modify, \
summarize, or wrap it in markdown. Output ONLY the JSON string.""",
    tools=[fetch_all_financial_data],
    output_key="financial_data",
)
