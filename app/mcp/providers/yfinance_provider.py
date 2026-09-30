import logging
import math

import yfinance as yf
from pydantic import BaseModel, field_validator

from app.mcp.providers.base import FinancialDataProvider

logger = logging.getLogger(__name__)


class _SanitizedPayload(BaseModel):
    """Base for provider payloads: numeric fields must be finite floats.

    yfinance frequently returns NaN (which survives float() and round()) or None
    for missing line items. Left alone, a single NaN poisons every downstream
    calculator and lands in the report unnoticed. Subclasses list their numeric
    fields; NaN/None are replaced with 0.0 and logged so a run with degraded
    inputs is visible, and downstream zero-divisor guards fail loudly instead.
    """

    @field_validator("*", mode="before")
    @classmethod
    def _replace_nan_and_none(cls, value, info):
        if cls.model_fields[info.field_name].annotation is not float:
            return value  # only numeric fields are sanitised
        if value is None or (isinstance(value, float) and math.isnan(value)):
            logger.warning(
                "yfinance returned %s for numeric field '%s' — replacing with 0.0",
                value, info.field_name,
            )
            return 0.0
        return value


class FinancialStatementsPayload(_SanitizedPayload):
    ticker: str
    company_name: str
    fiscal_year_end: str
    currency: str
    total_assets: float
    current_assets: float
    inventory: float
    cash: float
    accounts_receivable: float
    current_liabilities: float
    total_non_current_liabilities: float
    shareholders_equity: float
    total_revenue: float
    gross_profit: float
    net_income: float
    ebit: float
    interest_expense: float
    tax_expense: float
    pretax_income: float
    cfo: float
    capex: float
    non_cash_expenses: float


class MarketDataPayload(_SanitizedPayload):
    ticker: str
    company_name: str
    currency: str
    current_price: float
    shares_outstanding: float
    beta: float
    market_cap: float

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
    "e_commerce": 0.15,
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


def _get(df, *labels, col_name=None):
    """Return the fiscal-year value for the first matching label for col_name (or first column)."""
    for label in labels:
        if label in df.index:
            try:
                if col_name is not None and col_name in df.columns:
                    val = df.loc[label, col_name]
                else:
                    val = df.loc[label].iloc[0]
                if val is not None and not (isinstance(val, float) and val != val):
                    return float(val)
            except (TypeError, ValueError, IndexError, KeyError):
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

            # Determine which column represents the most recent completed fiscal year.
            # Yahoo Finance sometimes includes a forward placeholder column (e.g. unfiled future year)
            # where Total Revenue / Net Income is NaN. Skip such placeholder columns.
            target_col = income.columns[0]
            for col in income.columns:
                has_data = False
                for test_label in ("Total Revenue", "Operating Revenue", "Net Income"):
                    if test_label in income.index:
                        try:
                            val = income.loc[test_label, col]
                            if val is not None and not (isinstance(val, float) and val != val):
                                has_data = True
                                break
                        except Exception:
                            pass
                if has_data:
                    target_col = col
                    break

            fiscal_year_end = str(target_col.date())

            total_revenue   = _get(income,  "Total Revenue", col_name=target_col)
            gross_profit    = _get(income,  "Gross Profit", col_name=target_col)
            net_income      = _get(income,  "Net Income", col_name=target_col)
            ebit            = _get(income,  "EBIT", "Operating Income", col_name=target_col)
            interest_exp    = _get(income,  "Interest Expense", col_name=target_col)
            tax_expense     = _get(income,  "Tax Provision", "Income Tax Expense", col_name=target_col)
            pretax_income   = _get(income,  "Pretax Income", col_name=target_col)

            total_assets        = _get(balance, "Total Assets", col_name=target_col)
            current_assets      = _get(balance, "Current Assets", col_name=target_col)
            inventory           = _get(balance, "Inventory", col_name=target_col)
            cash                = _get(balance, "Cash And Cash Equivalents",
                                               "Cash Cash Equivalents And Short Term Investments", col_name=target_col)
            accounts_receivable = _get(balance, "Accounts Receivable", "Net Receivables", col_name=target_col)
            current_liabilities = _get(balance, "Current Liabilities", col_name=target_col)
            total_non_current_liabilities = _get(
                balance,
                "Total Non Current Liabilities Net Minority Interest",
                "Long Term Debt",
                col_name=target_col,
            )
            shareholders_equity = _get(balance, "Stockholders Equity",
                                               "Total Stockholder Equity", col_name=target_col)

            cfo          = _get(cashflow, "Operating Cash Flow", "Total Cash From Operating Activities", col_name=target_col)
            capex_raw    = _get(cashflow, "Capital Expenditure", col_name=target_col)
            non_cash_exp = _get(cashflow, "Depreciation And Amortization",
                                          "Depreciation Amortization Depletion", col_name=target_col)

            # capex and interest_expense must be returned as positive values
            capex            = abs(capex_raw)           if capex_raw    is not None else None
            interest_expense = abs(interest_exp)        if interest_exp is not None else None

            return FinancialStatementsPayload.model_validate({
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
            }).model_dump()

        except Exception as exc:
            return {"error": str(exc), "ticker": ns_ticker}

    def _calculate_historical_beta(self, ticker: str) -> float:
        """Calculate 5-year monthly beta using history() endpoint which bypasses Cloudflare."""
        import pandas as pd
        
        index_ticker = "^GSPC"
        if ticker.endswith(".NS"):
            index_ticker = "^NSEI"
        elif ticker.endswith(".BO"):
            index_ticker = "^BSESN"
            
        try:
            stock_data = yf.Ticker(ticker).history(period="5y", interval="1mo")['Close']
            market_data = yf.Ticker(index_ticker).history(period="5y", interval="1mo")['Close']
            
            df = pd.DataFrame({'Stock': stock_data, 'Market': market_data}).dropna()
            if len(df) < 12:
                return 1.0
                
            returns = df.pct_change().dropna()
            cov = returns['Stock'].cov(returns['Market'])
            var = returns['Market'].var()
            
            return float(cov / var)
        except Exception:
            return 1.0

    def get_market_data(self, ticker: str) -> dict:
        ns_ticker = _ensure_ns_suffix(ticker)
        try:
            stock = yf.Ticker(ns_ticker)
            info = stock.info or {}
            fast = stock.fast_info

            # fast_info is much more reliable than info (which often silently fails and returns {})
            try:
                current_price = fast.last_price
            except Exception:
                current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0

            try:
                shares_raw = fast.shares
            except Exception:
                shares_raw = info.get("sharesOutstanding")

            try:
                market_cap = fast.market_cap
            except Exception:
                market_cap = info.get("marketCap")

            beta = info.get("beta")
            if not beta or beta == 0.0:
                # If info endpoint fails (Cloudflare block), compute it manually via historical prices
                beta = self._calculate_historical_beta(ns_ticker)
                
            if not beta or beta == 0.0:
                beta = 1.0  # Final fallback

            # shares_outstanding in crore (1 crore = 10,000,000)
            shares_in_crore = (shares_raw / 10_000_000) if shares_raw is not None else 0.0

            return MarketDataPayload.model_validate({
                "ticker":             ns_ticker,
                "company_name":       info.get("longName", ""),
                "current_price":      _round2(current_price),
                "shares_outstanding": _round2(shares_in_crore),
                "beta":               _round2(beta),
                "market_cap":         _round2(market_cap),
                "currency":           info.get("currency", "INR"),
            }).model_dump()

        except Exception as exc:
            return {"error": str(exc), "ticker": ns_ticker}

    def get_sector_growth_rate(self, sector: str) -> float:
        key = sector.lower().replace(" ", "_").replace("/", "_")
        return _SECTOR_GROWTH_RATES.get(key, _SECTOR_GROWTH_RATES["default"])
