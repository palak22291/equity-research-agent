import yfinance as yf

from app.mcp.providers.base import FinancialDataProvider

_SECTOR_GROWTH_RATES = {
    "pharmaceuticals": 0.09,
    "it": 0.10,
    "banking": 0.13,
    "fmcg": 0.08,
    "automobiles": 0.06,
    "oil_gas": 0.05,
    "telecom": 0.07,
    "metals": 0.04,
    "cement": 0.07,
    "power": 0.05,
    "healthcare": 0.11,
    "default": 0.08,
}

# Indian exchange suffixes that already carry a country designation.
_INDIAN_SUFFIXES = {".NS", ".BO"}


def _ensure_ns_suffix(ticker: str) -> str:
    upper = ticker.upper()
    if any(upper.endswith(s) for s in _INDIAN_SUFFIXES):
        return ticker
    # Heuristic: if the raw ticker resolves on NSE, add .NS.
    # We always add .NS here; callers that want BSE can pass the suffix explicitly.
    return ticker + ".NS"


def _round2(value) -> float:
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _get(df, *labels):
    """Return the most recent fiscal-year value for the first matching label."""
    for label in labels:
        if label in df.index:
            val = df.loc[label].iloc[0]
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return None


class YFinanceProvider(FinancialDataProvider):

    def get_financial_statements(self, ticker: str) -> dict:
        ns_ticker = _ensure_ns_suffix(ticker)
        try:
            stock = yf.Ticker(ns_ticker)
            info = stock.info or {}

            income = stock.financials          # columns = fiscal year ends, rows = line items
            balance = stock.balance_sheet
            cashflow = stock.cashflow

            if income is None or income.empty:
                return {"error": f"No income statement data for {ns_ticker}"}
            if balance is None or balance.empty:
                return {"error": f"No balance sheet data for {ns_ticker}"}
            if cashflow is None or cashflow.empty:
                return {"error": f"No cash flow data for {ns_ticker}"}

            # Most recent fiscal year only (iloc[:, 0])
            fiscal_year_end = str(income.columns[0].date())

            total_revenue   = _get(income,  "Total Revenue")
            gross_profit    = _get(income,  "Gross Profit")
            net_income      = _get(income,  "Net Income")
            ebit            = _get(income,  "EBIT", "Operating Income")
            interest_exp    = _get(income,  "Interest Expense")
            tax_expense     = _get(income,  "Tax Provision", "Income Tax Expense")
            pretax_income   = _get(income,  "Pretax Income")

            total_assets        = _get(balance, "Total Assets")
            current_assets      = _get(balance, "Current Assets")
            inventory           = _get(balance, "Inventory")
            cash                = _get(balance, "Cash And Cash Equivalents",
                                               "Cash Cash Equivalents And Short Term Investments")
            accounts_receivable = _get(balance, "Accounts Receivable", "Net Receivables")
            current_liabilities = _get(balance, "Current Liabilities")
            total_non_current_liabilities = _get(
                balance,
                "Total Non Current Liabilities Net Minority Interest",
                "Long Term Debt",
            )
            shareholders_equity = _get(balance, "Stockholders Equity",
                                               "Total Stockholder Equity")

            cfo          = _get(cashflow, "Operating Cash Flow", "Total Cash From Operating Activities")
            capex_raw    = _get(cashflow, "Capital Expenditure")
            non_cash_exp = _get(cashflow, "Depreciation And Amortization",
                                          "Depreciation Amortization Depletion")

            # capex and interest_expense must be returned as positive values
            capex            = abs(capex_raw)           if capex_raw    is not None else None
            interest_expense = abs(interest_exp)        if interest_exp is not None else None

            return {
                "ticker":                      ns_ticker,
                "company_name":                info.get("longName", ""),
                "fiscal_year_end":             fiscal_year_end,
                "currency":                    info.get("currency", "INR"),
                "total_assets":                _round2(total_assets),
                "current_assets":              _round2(current_assets),
                "inventory":                   _round2(inventory),
                "cash":                        _round2(cash),
                "accounts_receivable":         _round2(accounts_receivable),
                "current_liabilities":         _round2(current_liabilities),
                "total_non_current_liabilities": _round2(total_non_current_liabilities),
                "shareholders_equity":         _round2(shareholders_equity),
                "total_revenue":               _round2(total_revenue),
                "gross_profit":                _round2(gross_profit),
                "net_income":                  _round2(net_income),
                "ebit":                        _round2(ebit),
                "interest_expense":            _round2(interest_expense),
                "tax_expense":                 _round2(tax_expense),
                "pretax_income":               _round2(pretax_income),
                "cfo":                         _round2(cfo),
                "capex":                       _round2(capex),
                "non_cash_expenses":           _round2(non_cash_exp),
            }

        except Exception as exc:
            return {"error": str(exc), "ticker": ns_ticker}

    def get_market_data(self, ticker: str) -> dict:
        ns_ticker = _ensure_ns_suffix(ticker)
        try:
            stock = yf.Ticker(ns_ticker)
            info = stock.info or {}

            current_price     = info.get("currentPrice") or info.get("regularMarketPrice")
            shares_raw        = info.get("sharesOutstanding")
            beta              = info.get("beta")
            market_cap        = info.get("marketCap")

            # shares_outstanding in crore (1 crore = 10,000,000)
            shares_in_crore = (shares_raw / 10_000_000) if shares_raw is not None else None

            return {
                "ticker":             ns_ticker,
                "company_name":       info.get("longName", ""),
                "current_price":      _round2(current_price),
                "shares_outstanding": _round2(shares_in_crore),
                "beta":               _round2(beta),
                "market_cap":         _round2(market_cap),
                "currency":           info.get("currency", "INR"),
            }

        except Exception as exc:
            return {"error": str(exc), "ticker": ns_ticker}

    def get_sector_growth_rate(self, sector: str) -> float:
        key = sector.lower().replace(" ", "_").replace("/", "_")
        return _SECTOR_GROWTH_RATES.get(key, _SECTOR_GROWTH_RATES["default"])
