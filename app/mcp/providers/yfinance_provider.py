import hashlib
import json as _json
import logging
import math
import os
import time
from pathlib import Path

import yfinance as yf
from pydantic import BaseModel, field_validator

from app.mcp.providers.base import FinancialDataProvider

logger = logging.getLogger(__name__)

# ── yfinance response cache ──────────────────────────────────────────────────
# Yahoo Finance aggressively rate-limits cloud/shared IPs (Render, Railway, etc).
# We cache successful responses to disk so subsequent requests for the same ticker
# serve instantly from cache instead of failing with 429.
# Cache TTL: 24 hours (financial statements change at most quarterly).
_CACHE_DIR = Path(os.environ.get("YFINANCE_CACHE_DIR",
                                  Path(__file__).resolve().parents[2] / "data" / "yfinance_cache"))
_CACHE_TTL_SECONDS = int(os.environ.get("YFINANCE_CACHE_TTL", 86400))  # 24h default


def _cache_key(prefix: str, ticker: str) -> Path:
    """Return the cache file path for a given prefix + ticker."""
    safe = hashlib.md5(f"{prefix}:{ticker}".encode()).hexdigest()[:12]
    return _CACHE_DIR / f"{prefix}_{ticker.replace('.', '_')}_{safe}.json"


def _read_cache(path: Path) -> dict | None:
    """Read cache file if it exists and hasn't expired."""
    if not path.exists():
        return None
    try:
        age = time.time() - path.stat().st_mtime
        if age > _CACHE_TTL_SECONDS:
            return None  # expired
        return _json.loads(path.read_text())
    except Exception:
        return None


def _write_cache(path: Path, data: dict) -> None:
    """Write data to cache file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps(data))
    except Exception as exc:
        logger.warning("Failed to write yfinance cache: %s", exc)


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
        cache_path = _cache_key("statements", ns_ticker)
        last_error = None
        for attempt in range(4):  # up to 4 attempts (initial + 3 retries)
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

                payload = FinancialStatementsPayload.model_validate({
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
                })
                result = payload.model_dump()

                # Cache successful response for future rate-limited requests.
                _write_cache(cache_path, result)
                return result

            except Exception as exc:
                last_error = str(exc)
                # Retry on rate limits (Yahoo Finance 429s common on shared IPs)
                if "Too Many Requests" in last_error or "429" in last_error:
                    wait = 5 * (2 ** attempt)  # 5s, 10s, 20s, 40s
                    logger.warning(
                        "yfinance rate limited (attempt %d/4), retrying in %ds: %s",
                        attempt + 1, wait, last_error,
                    )
                    time.sleep(wait)
                    continue
                return {"error": last_error, "ticker": ns_ticker}

        # All retries exhausted — fall back to cache (even if expired).
        cached = _read_cache(cache_path)
        if cached is None:
            # Try reading without TTL check as last resort.
            try:
                if cache_path.exists():
                    cached = _json.loads(cache_path.read_text())
            except Exception:
                pass
        if cached:
            logger.info("Serving cached yfinance data for %s (rate limited)", ns_ticker)
            return cached
        return {"error": f"yfinance rate limited after 4 attempts: {last_error}", "ticker": ns_ticker}

    def get_market_data(self, ticker: str) -> dict:
        ns_ticker = _ensure_ns_suffix(ticker)
        cache_path = _cache_key("market", ns_ticker)
        last_error = None
        for attempt in range(4):
            try:
                stock = yf.Ticker(ns_ticker)
                info = stock.info or {}

                current_price     = info.get("currentPrice") or info.get("regularMarketPrice")
                shares_raw        = info.get("sharesOutstanding")
                beta              = info.get("beta")
                market_cap        = info.get("marketCap")

                # shares_outstanding in crore (1 crore = 10,000,000)
                shares_in_crore = (shares_raw / 10_000_000) if shares_raw is not None else None

                result = MarketDataPayload.model_validate({
                    "ticker":             ns_ticker,
                    "company_name":       info.get("longName", ""),
                    "current_price":      _round2(current_price),
                    "shares_outstanding": _round2(shares_in_crore),
                    "beta":               _round2(beta),
                    "market_cap":         _round2(market_cap),
                    "currency":           info.get("currency", "INR"),
                }).model_dump()

                _write_cache(cache_path, result)
                return result

            except Exception as exc:
                last_error = str(exc)
                if "Too Many Requests" in last_error or "429" in last_error:
                    wait = 5 * (2 ** attempt)
                    logger.warning(
                        "yfinance market data rate limited (attempt %d/4), retrying in %ds",
                        attempt + 1, wait,
                    )
                    time.sleep(wait)
                    continue
                return {"error": last_error, "ticker": ns_ticker}

        # All retries exhausted — fall back to cache (even if expired).
        cached = _read_cache(cache_path)
        if cached is None:
            try:
                if cache_path.exists():
                    cached = _json.loads(cache_path.read_text())
            except Exception:
                pass
        if cached:
            logger.info("Serving cached market data for %s (rate limited)", ns_ticker)
            return cached
        return {"error": f"yfinance rate limited after 4 attempts: {last_error}", "ticker": ns_ticker}

    def get_sector_growth_rate(self, sector: str) -> float:
        key = sector.lower().replace(" ", "_").replace("/", "_")
        return _SECTOR_GROWTH_RATES.get(key, _SECTOR_GROWTH_RATES["default"])
