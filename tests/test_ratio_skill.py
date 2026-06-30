"""Skill-level tests for the ratio-analysis script (the subprocess wired into the agent).

These cover graceful degradation that lives in the skill, not the pure calculator:
a no-inventory / debt-free company (e.g. an IT services firm like Infosys) must
produce N/A for inventory- and interest-based ratios rather than aborting the whole
analysis — a fatal error there makes the analysis agent retry, which wastes the Groq
TPM budget and can tempt the LLM to fudge a non-zero input.
"""
import json
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _PROJECT_ROOT / "app/skills/ratio-analysis/scripts/calculate_ratios.py"

# Infosys-like profile: no inventory, negligible/zero interest expense.
_IT_FIRM_INPUT = {
    "total_assets": 16_446_000_000,
    "current_assets": 10_912_000_000,
    "inventory": 0,
    "cash": 2_341_000_000,
    "accounts_receivable": 3_715_000_000,
    "current_liabilities": 5_516_000_000,
    "total_non_current_liabilities": 2_000_000_000,
    "shareholders_equity": 9_000_000_000,
    "total_revenue": 20_158_000_000,
    "gross_profit": 6_079_000_000,
    "net_income": 3_313_000_000,
    "ebit": 4_553_000_000,
    "interest_expense": 0,
    "current_price": 1_500,
    "shares_outstanding": 415,
}


def _run(payload: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(_PROJECT_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_zero_inventory_does_not_abort():
    """A no-inventory firm yields N/A for inventory ratios, not a fatal error."""
    out = _run(_IT_FIRM_INPUT)
    assert "error" not in out, out
    assert out["efficiency"]["inventory_turnover"] is None
    # Core ratios still compute from the data that *is* present.
    assert out["liquidity"]["current_ratio"] is not None
    assert out["profitability"]["net_profit_margin"] is not None


def test_zero_interest_expense_yields_na_coverage():
    """A debt-free firm with no interest expense yields N/A interest coverage."""
    out = _run(_IT_FIRM_INPUT)
    assert "error" not in out, out
    assert out["solvency"]["interest_coverage"] is None


def test_null_inventory_is_handled_like_zero():
    """yfinance returns null inventory for some firms — must not crash."""
    payload = dict(_IT_FIRM_INPUT, inventory=None)
    out = _run(payload)
    assert "error" not in out, out
    assert out["efficiency"]["inventory_turnover"] is None
