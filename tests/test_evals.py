"""End-to-end eval of the offline pipeline against the Cipla FY2026 fixture.

Runs the same deterministic path the --offline pipeline takes — OfflineDataAgent
for the data step, then the exact agent tool functions (which shell out to the
Agent Skill scripts) for analysis and valuation — with no Groq / LLM calls and
no network. The LLM's only role in the real pipeline is extracting literal
numbers from state and narrating; the numbers asserted here are produced by the
identical calculator chain.

Expected values are the FY2026 fixture's verified outputs (see README "Sample
Output": intrinsic ₹3,462, current ratio 3.44). NOTE: the FY2025 professor-graded
reference numbers (intrinsic ₹4,934.01, WACC 8.40%, Ke 8.44%) belong to the
FY2025 Excel inputs (FCFE 1,571.02 Cr, beta ≈ 0.31) and are asserted by the
per-calculator unit tests — they are NOT reachable from the FY2026 fixture
(beta 0.4468, validated FCFE 2,900.62 Cr), so this eval pins the FY2026 ground
truth instead.
"""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.analysis_agent import run_cashflow_analysis, run_ratio_analysis
from app.agents.offline_data_agent import create_offline_data_agent
from app.agents.valuation_agent import run_valuation

_FIXTURE = Path(__file__).resolve().parents[1] / "app" / "data" / "cipla_fy2026.json"

# ── Expected values (Cipla FY2026 fixture ground truth) ─────────────────────
EXPECTED_INTRINSIC_PRICE = 3462.73   # INR/share (README sample output: ₹3,462)
EXPECTED_VERDICT         = "Undervalued"
EXPECTED_CURRENT_RATIO   = 3.44
EXPECTED_WACC            = 0.0900    # 9.00% (FY2025 reference 8.40% needs FY2025 inputs)
EXPECTED_FCFF            = 2585.67   # INR crore, validated across 3 methods

# ── Tolerances ───────────────────────────────────────────────────────────────
PRICE_REL_TOL         = 0.10    # ±10%
CURRENT_RATIO_ABS_TOL = 0.1
WACC_ABS_TOL          = 0.005   # ±0.5 percentage points
FCFF_REL_TOL          = 0.10    # ±10%


async def _run_data_step() -> dict:
    """Run the real OfflineDataAgent and return the financial data it writes
    to temp:financial_data (the same payload the downstream agents read)."""
    agent = create_offline_data_agent()
    ctx = SimpleNamespace(invocation_id="eval-offline-run")
    events = [event async for event in agent._run_async_impl(ctx)]
    assert len(events) == 1, f"OfflineDataAgent emitted {len(events)} events, expected 1"
    payload = events[0].actions.state_delta["temp:financial_data"]
    return json.loads(payload)


@pytest.fixture(scope="module")
def pipeline_outputs() -> dict:
    """Run the offline pipeline once and share its outputs across all evals.

    Mirrors the orchestrator's sequence: data → analysis (ratios + cashflows)
    → valuation (cost of capital + DCF). Each step consumes the previous
    step's output exactly as the agents' instructions direct the LLM to.
    """
    financial = asyncio.run(_run_data_step())
    assert "error" not in financial, f"data step failed: {financial}"

    ratios = json.loads(run_ratio_analysis(
        total_assets=financial["total_assets"],
        current_assets=financial["current_assets"],
        inventory=financial["inventory"],
        cash=financial["cash"],
        accounts_receivable=financial["accounts_receivable"],
        current_liabilities=financial["current_liabilities"],
        total_non_current_liabilities=financial["total_non_current_liabilities"],
        shareholders_equity=financial["shareholders_equity"],
        total_revenue=financial["total_revenue"],
        gross_profit=financial["gross_profit"],
        net_income=financial["net_income"],
        ebit=financial["ebit"],
        interest_expense=financial["interest_expense"],
        cfo=financial["cfo"],
        current_price=financial["current_price"],
        shares_outstanding=financial["shares_outstanding"],
    ))
    assert "error" not in ratios, f"ratio analysis failed: {ratios}"

    cashflows = json.loads(run_cashflow_analysis(
        net_income=financial["net_income"],
        non_cash_expenses=financial["non_cash_expenses"],
        cfo=financial["cfo"],
        capex=financial["capex"],
        ebit=financial["ebit"],
        interest_expense=financial["interest_expense"],
        tax_expense=financial["tax_expense"],
        pretax_income=financial["pretax_income"],
        increase_in_current_assets=financial["increase_in_current_assets"],
        increase_in_current_liabilities=financial["increase_in_current_liabilities"],
        net_borrowing=financial["net_borrowing"],
    ))
    assert "error" not in cashflows, f"cashflow analysis failed: {cashflows}"

    valuation = json.loads(run_valuation(
        beta=financial["beta"],
        risk_free_rate=financial["risk_free_rate"],
        market_return=financial["market_return"],
        interest_expense=financial["interest_expense"],
        total_non_current_liabilities=financial["total_non_current_liabilities"],
        shareholders_equity=financial["shareholders_equity"],
        tax_expense=financial["tax_expense"],
        pretax_income=financial["pretax_income"],
        fcfe=cashflows["fcfe"]["validated_fcfe"],
        fcff=cashflows["fcff"]["validated_fcff"],
        growth_rate=financial["growth_rate"],
        shares_outstanding=financial["shares_outstanding"],
        current_price=financial["current_price"],
        years=3,
    ))
    assert "error" not in valuation, f"valuation failed: {valuation}"
    assert "error" not in valuation["dcf_valuation"], f"DCF failed: {valuation['dcf_valuation']}"

    return {
        "financial": financial,
        "ratios": ratios,
        "cashflows": cashflows,
        "cost_of_capital": valuation["cost_of_capital"],
        "dcf": valuation["dcf_valuation"],
    }


def test_fixture_is_offline_source(pipeline_outputs):
    """The data step served the cached fixture — right company, no network."""
    financial = pipeline_outputs["financial"]
    reference = json.loads(_FIXTURE.read_text())
    assert financial["ticker"] == "CIPLA.NS"
    assert financial == reference


def test_intrinsic_price(pipeline_outputs):
    """Eval 1: intrinsic share price within 10% of the fixture ground truth."""
    price = pipeline_outputs["dcf"]["equity_valuation"]["intrinsic_share_price"]
    assert price == pytest.approx(EXPECTED_INTRINSIC_PRICE, rel=PRICE_REL_TOL), (
        f"intrinsic price {price} outside ±{PRICE_REL_TOL:.0%} of {EXPECTED_INTRINSIC_PRICE}"
    )


def test_verdict_undervalued(pipeline_outputs):
    """Eval 2: DCF verdict is Undervalued (intrinsic well above market price)."""
    assert pipeline_outputs["dcf"]["equity_valuation"]["verdict"] == EXPECTED_VERDICT


def test_current_ratio(pipeline_outputs):
    """Eval 3: current ratio matches 3.44 ± 0.1."""
    ratio = pipeline_outputs["ratios"]["liquidity"]["current_ratio"]
    assert ratio == pytest.approx(EXPECTED_CURRENT_RATIO, abs=CURRENT_RATIO_ABS_TOL), (
        f"current ratio {ratio} outside {EXPECTED_CURRENT_RATIO} ± {CURRENT_RATIO_ABS_TOL}"
    )


def test_wacc(pipeline_outputs):
    """Eval 4: WACC within 0.5 percentage points of the fixture ground truth."""
    wacc = pipeline_outputs["cost_of_capital"]["wacc"]
    assert wacc == pytest.approx(EXPECTED_WACC, abs=WACC_ABS_TOL), (
        f"WACC {wacc:.4%} outside {EXPECTED_WACC:.2%} ± {WACC_ABS_TOL:.2%}"
    )


def test_validated_fcff(pipeline_outputs):
    """Eval 5: cross-validated FCFF within 10% of 2,585.67 crore."""
    fcff = pipeline_outputs["cashflows"]["fcff"]["validated_fcff"]
    assert fcff == pytest.approx(EXPECTED_FCFF, rel=FCFF_REL_TOL), (
        f"validated FCFF {fcff} outside ±{FCFF_REL_TOL:.0%} of {EXPECTED_FCFF}"
    )
