"""Valuation agent — computes WACC, cost of equity, DCF intrinsic value, and verdict.

Rewritten as an LLM-free BaseAgent. The previous LlmAgent used Groq's 70B
model just to extract JSON fields and pass them to the run_valuation function.
This consumed thousands of TPM tokens for a purely mechanical job. Now it
calls the skill scripts directly in Python: zero Groq tokens, zero rate-limit
risk.
"""
import json
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from app.skills.runner import run_skill

_COST_OF_CAPITAL_SKILL = "app/skills/cost-of-capital/scripts/calculate_cost_of_capital.py"
_VALUATION_SKILL = "app/skills/valuation/scripts/calculate_valuation.py"


class ValuationAgent(BaseAgent):
    """Computes cost of capital and DCF valuation deterministically (no LLM).

    Reads temp:financial_data and temp:analysis_results from session state,
    extracts the required numeric fields, chains the two skill scripts, and
    writes the combined result to temp:valuation_results.
    """

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        # Read inputs from session state.
        fd_raw = ctx.session.state.get("temp:financial_data", "{}")
        ar_raw = ctx.session.state.get("temp:analysis_results", "{}")

        try:
            fd = json.loads(fd_raw) if isinstance(fd_raw, str) else fd_raw
        except (json.JSONDecodeError, TypeError):
            fd = {}
        try:
            ar = json.loads(ar_raw) if isinstance(ar_raw, str) else ar_raw
        except (json.JSONDecodeError, TypeError):
            ar = {}

        # --- Cost of capital ---
        coc_raw = run_skill(_COST_OF_CAPITAL_SKILL, {
            "beta": fd.get("beta", 0),
            "risk_free_rate": fd.get("risk_free_rate", 0.0685),
            "market_return": fd.get("market_return", 0.12),
            "interest_expense": fd.get("interest_expense", 0),
            "total_non_current_liabilities": fd.get("total_non_current_liabilities", 0),
            "shareholders_equity": fd.get("shareholders_equity", 0),
            "tax_expense": fd.get("tax_expense", 0),
            "pretax_income": fd.get("pretax_income", 0),
        })

        try:
            coc = json.loads(coc_raw)
        except (json.JSONDecodeError, TypeError):
            payload = json.dumps({"error": f"cost-of-capital skill returned non-JSON: {coc_raw!r}"})
            yield self._emit(ctx, payload)
            return

        if "error" in coc:
            payload = json.dumps({"error": f"cost of capital failed: {coc['error']}"})
            yield self._emit(ctx, payload)
            return

        ke = coc.get("ke")
        wacc = coc.get("wacc")
        if not ke or not wacc:
            payload = json.dumps({"error": f"cost of capital returned non-positive ke ({ke}) / wacc ({wacc})"})
            yield self._emit(ctx, payload)
            return

        # --- Extract validated FCFE/FCFF from analysis results ---
        cashflow = ar.get("cashflow_analysis", {})
        fcfe = cashflow.get("fcfe", {}).get("validated_fcfe", 0)
        fcff = cashflow.get("fcff", {}).get("validated_fcff", 0)

        # --- DCF valuation ---
        dcf_raw = run_skill(_VALUATION_SKILL, {
            "fcfe": fcfe,
            "fcff": fcff,
            "ke": ke,
            "wacc": wacc,
            "growth_rate": fd.get("growth_rate", 0.05),
            "shares_outstanding": fd.get("shares_outstanding", 0),
            "current_price": fd.get("current_price", 0),
            "terminal_growth_rate": 0.0,
            "years": 3,
        })

        try:
            dcf = json.loads(dcf_raw)
        except (json.JSONDecodeError, TypeError):
            payload = json.dumps({"error": f"valuation skill returned non-JSON: {dcf_raw!r}"})
            yield self._emit(ctx, payload)
            return

        combined = {"cost_of_capital": coc, "dcf_valuation": dcf}
        payload = json.dumps(combined)
        yield self._emit(ctx, payload)

    def _emit(self, ctx: InvocationContext, payload: str) -> Event:
        return Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=types.Content(role="model", parts=[types.Part(text=payload)]),
            actions=EventActions(state_delta={"temp:valuation_results": payload}),
        )


def create_valuation_agent() -> ValuationAgent:
    return ValuationAgent(name="valuation_agent")


# ── Standalone wrapper (used by tests / evals) ──────────────────────────────

def run_valuation(
    beta: float,
    risk_free_rate: float,
    market_return: float,
    interest_expense: float,
    total_non_current_liabilities: float,
    shareholders_equity: float,
    tax_expense: float,
    pretax_income: float,
    fcfe: float,
    fcff: float,
    growth_rate: float,
    shares_outstanding: float,
    current_price: float,
    years: int = 3,
) -> str:
    """Compute cost of capital then DCF valuation. Same interface as the old
    LlmAgent tool function — used by tests and evals."""
    coc_raw = run_skill(_COST_OF_CAPITAL_SKILL, {
        "beta": beta,
        "risk_free_rate": risk_free_rate,
        "market_return": market_return,
        "interest_expense": interest_expense,
        "total_non_current_liabilities": total_non_current_liabilities,
        "shareholders_equity": shareholders_equity,
        "tax_expense": tax_expense,
        "pretax_income": pretax_income,
    })

    try:
        coc = json.loads(coc_raw)
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"error": f"cost-of-capital skill returned non-JSON: {coc_raw!r}"})

    if "error" in coc:
        return json.dumps({"error": f"cost of capital failed: {coc['error']}"})

    ke = coc.get("ke")
    wacc = coc.get("wacc")
    if not ke or not wacc:
        return json.dumps({"error": f"cost of capital returned non-positive ke ({ke}) / wacc ({wacc})"})

    dcf_raw = run_skill(_VALUATION_SKILL, {
        "fcfe": fcfe,
        "fcff": fcff,
        "ke": ke,
        "wacc": wacc,
        "growth_rate": growth_rate,
        "shares_outstanding": shares_outstanding,
        "current_price": current_price,
        "terminal_growth_rate": 0.0,
        "years": years,
    })

    try:
        dcf = json.loads(dcf_raw)
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"error": f"valuation skill returned non-JSON: {dcf_raw!r}"})

    return json.dumps({"cost_of_capital": coc, "dcf_valuation": dcf})


valuation_agent = create_valuation_agent()
