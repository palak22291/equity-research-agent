"""Analysis agent — runs ratio analysis and cash flow calculations.

Rewritten as an LLM-free BaseAgent. The previous LlmAgent used Groq's 70B
model just to extract JSON fields and pass them to tool functions — a
mechanical job that consumed ~11k of the 12k TPM budget per run, causing
persistent rate-limit failures. This agent now calls the skill functions
directly in Python: zero Groq tokens, zero rate-limit risk.
"""
import json
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from app.skills.runner import run_skill

_RATIO_SKILL = "app/skills/ratio-analysis/scripts/calculate_ratios.py"
_CASHFLOW_SKILL = "app/skills/cashflow-analysis/scripts/calculate_cashflows.py"


class AnalysisAgent(BaseAgent):
    """Runs ratio analysis and cashflow analysis deterministically (no LLM).

    Reads temp:financial_data from session state, extracts the required numeric
    fields, calls the two skill scripts, and writes the combined result to
    temp:analysis_results.
    """

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        # Read financial data from the previous agent's state output.
        fd_raw = ctx.session.state.get("temp:financial_data", "{}")
        try:
            fd = json.loads(fd_raw) if isinstance(fd_raw, str) else fd_raw
        except (json.JSONDecodeError, TypeError):
            fd = {}

        # --- Ratio analysis ---
        ratio_raw = run_skill(_RATIO_SKILL, {
            "total_assets": fd.get("total_assets", 0),
            "current_assets": fd.get("current_assets", 0),
            "inventory": fd.get("inventory", 0),
            "cash": fd.get("cash", 0),
            "accounts_receivable": fd.get("accounts_receivable", 0),
            "current_liabilities": fd.get("current_liabilities", 0),
            "total_non_current_liabilities": fd.get("total_non_current_liabilities", 0),
            "shareholders_equity": fd.get("shareholders_equity", 0),
            "total_revenue": fd.get("total_revenue", 0),
            "gross_profit": fd.get("gross_profit", 0),
            "net_income": fd.get("net_income", 0),
            "ebit": fd.get("ebit", 0),
            "interest_expense": fd.get("interest_expense", 0),
            "cfo": fd.get("cfo", 0),
            "current_price": fd.get("current_price", 0),
            "shares_outstanding": fd.get("shares_outstanding", 0),
        })

        # --- Cashflow analysis ---
        cashflow_raw = run_skill(_CASHFLOW_SKILL, {
            "net_income": fd.get("net_income", 0),
            "non_cash_expenses": fd.get("non_cash_expenses", 0),
            "cfo": fd.get("cfo", 0),
            "capex": fd.get("capex", 0),
            "ebit": fd.get("ebit", 0),
            "interest_expense": fd.get("interest_expense", 0),
            "tax_expense": fd.get("tax_expense", 0),
            "pretax_income": fd.get("pretax_income", 0),
            "increase_in_current_assets": fd.get("increase_in_current_assets", 0),
            "increase_in_current_liabilities": fd.get("increase_in_current_liabilities", 0),
            "net_borrowing": fd.get("net_borrowing", 0),
        })

        # Parse results
        try:
            ratio_result = json.loads(ratio_raw)
        except (json.JSONDecodeError, TypeError):
            ratio_result = {"error": f"ratio skill returned non-JSON: {ratio_raw!r}"}

        try:
            cashflow_result = json.loads(cashflow_raw)
        except (json.JSONDecodeError, TypeError):
            cashflow_result = {"error": f"cashflow skill returned non-JSON: {cashflow_raw!r}"}

        combined = {
            "ratio_analysis": ratio_result,
            "cashflow_analysis": cashflow_result,
        }
        payload = json.dumps(combined)

        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=types.Content(role="model", parts=[types.Part(text=payload)]),
            actions=EventActions(state_delta={"temp:analysis_results": payload}),
        )


def create_analysis_agent() -> AnalysisAgent:
    return AnalysisAgent(name="analysis_agent")


# ── Standalone wrappers (used by tests / evals) ─────────────────────────────

def run_ratio_analysis(**kwargs) -> str:
    """Call the ratio-analysis skill directly. Accepts the same keyword args
    that the old LlmAgent tool function did."""
    return run_skill(_RATIO_SKILL, kwargs)


def run_cashflow_analysis(**kwargs) -> str:
    """Call the cashflow-analysis skill directly."""
    return run_skill(_CASHFLOW_SKILL, kwargs)


analysis_agent = create_analysis_agent()
