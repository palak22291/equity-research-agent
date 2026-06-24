"""
FastMCP server exposing financial data tools backed by YFinanceProvider.

Run with:
    python -m app.mcp.financial_data_server
or via MCP client configuration pointing to this module.
"""

from fastmcp import FastMCP

from app.mcp.providers.yfinance_provider import YFinanceProvider

mcp = FastMCP("equity-research-financial-data")
_provider = YFinanceProvider()


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


if __name__ == "__main__":
    mcp.run()
