"""Provider payload sanitization: NaN/None numeric fields become 0.0 with a warning.

yfinance's NaN survives float() and round(), so unchecked it flows through every
calculator into the report. The pydantic payload models are the boundary guard.
No network: the models are validated directly with synthetic payloads.
"""
import json
import logging
import math
import subprocess
import sys
from pathlib import Path

import pytest

from app.mcp.providers.yfinance_provider import (
    FinancialStatementsPayload,
    MarketDataPayload,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_COC_SCRIPT = _PROJECT_ROOT / "app/skills/cost-of-capital/scripts/calculate_cost_of_capital.py"

_STATEMENTS = {
    "ticker": "TEST.NS", "company_name": "Test Ltd",
    "fiscal_year_end": "2026-03-31", "currency": "INR",
    "total_assets": 100.0, "current_assets": 50.0, "inventory": 10.0,
    "cash": 5.0, "accounts_receivable": 8.0, "current_liabilities": 20.0,
    "total_non_current_liabilities": 15.0, "shareholders_equity": 60.0,
    "total_revenue": 80.0, "gross_profit": 40.0, "net_income": 10.0,
    "ebit": 14.0, "interest_expense": 1.0, "tax_expense": 3.0,
    "pretax_income": 13.0, "cfo": 12.0, "capex": 6.0, "non_cash_expenses": 4.0,
}

_MARKET = {
    "ticker": "TEST.NS", "company_name": "Test Ltd", "currency": "INR",
    "current_price": 100.0, "shares_outstanding": 10.0,
    "beta": 0.9, "market_cap": 1000.0,
}


def test_nan_numeric_field_becomes_zero(caplog):
    payload = dict(_STATEMENTS, inventory=float("nan"))
    with caplog.at_level(logging.WARNING):
        out = FinancialStatementsPayload.model_validate(payload).model_dump()
    assert out["inventory"] == 0.0
    assert "inventory" in caplog.text and "replacing with 0.0" in caplog.text


def test_none_numeric_field_becomes_zero(caplog):
    payload = dict(_MARKET, beta=None)
    with caplog.at_level(logging.WARNING):
        out = MarketDataPayload.model_validate(payload).model_dump()
    assert out["beta"] == 0.0
    assert "beta" in caplog.text


def test_no_nan_survives_anywhere():
    payload = dict(_STATEMENTS, **{k: float("nan") for k in
                   ("total_assets", "cfo", "pretax_income", "gross_profit")})
    out = FinancialStatementsPayload.model_validate(payload).model_dump()
    assert not any(isinstance(v, float) and math.isnan(v) for v in out.values())


def test_clean_payload_passes_through_unchanged():
    out = FinancialStatementsPayload.model_validate(_STATEMENTS).model_dump()
    assert out == _STATEMENTS


def test_string_fields_are_not_sanitized():
    """The 0.0 replacement applies to numeric fields only — metadata stays intact."""
    out = FinancialStatementsPayload.model_validate(_STATEMENTS).model_dump()
    assert out["ticker"] == "TEST.NS"
    assert out["company_name"] == "Test Ltd"


# ── Loss-making guard in the cost-of-capital skill ───────────────────────────

_COC_INPUT = {
    "interest_expense": 482_300_000.0,
    "total_non_current_liabilities": 9_621_500_000.0,
    "shareholders_equity": 344_319_500_000.0,
    "tax_expense": 13_538_400_000.0,
    "pretax_income": 52_236_300_000.0,
    "risk_free_rate": 0.0685,
    "beta": 0.4468,
    "market_return": 0.12,
}


def _run_coc(payload: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, str(_COC_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True, text=True, cwd=str(_PROJECT_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.parametrize("pretax", [0.0, -52_236_300_000.0])
def test_loss_making_company_is_rejected(pretax):
    out = _run_coc(dict(_COC_INPUT, pretax_income=pretax))
    assert "error" in out
    assert "Cannot compute cost of capital for loss-making company" in out["error"]


def test_profitable_company_still_computes():
    out = _run_coc(_COC_INPUT)
    assert "error" not in out, out
    assert out["wacc"] == pytest.approx(0.0900, abs=0.005)
