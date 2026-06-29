"""Valuation agent — computes WACC, cost of equity, DCF intrinsic value, and verdict.

The tool functions are thin wrappers that invoke the Agent Skill scripts under
app/skills/ as subprocesses; all deterministic math lives in those scripts.
"""
import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app.skills.runner import run_skill

_COST_OF_CAPITAL_SKILL = "app/skills/cost-of-capital/scripts/calculate_cost_of_capital.py"
_VALUATION_SKILL = "app/skills/valuation/scripts/calculate_valuation.py"


def calculate_cost_of_capital(
    beta: float,
    risk_free_rate: float,
    market_return: float,
    interest_expense: float,
    total_non_current_liabilities: float,
    shareholders_equity: float,
    tax_expense: float,
    pretax_income: float,
) -> str:
    """Compute WACC, cost of equity (Ke), and cost of debt (Kd) using CAPM.

    Monetary parameters (interest_expense, total_non_current_liabilities,
    shareholders_equity, tax_expense, pretax_income) are raw INR as returned
    by yfinance. beta, risk_free_rate, and market_return are decimals.

    Returns:
        JSON string with top-level ke, kd, wacc fields plus breakdown details.
    """
    return run_skill(_COST_OF_CAPITAL_SKILL, {
        "beta": beta,
        "risk_free_rate": risk_free_rate,
        "market_return": market_return,
        "interest_expense": interest_expense,
        "total_non_current_liabilities": total_non_current_liabilities,
        "shareholders_equity": shareholders_equity,
        "tax_expense": tax_expense,
        "pretax_income": pretax_income,
    })


def run_dcf_valuation(
    fcfe: float,
    fcff: float,
    ke: float,
    wacc: float,
    growth_rate: float,
    shares_outstanding: float,
    current_price: float,
    terminal_growth_rate: float = 0.0,
    years: int = 3,
) -> str:
    """Run the DCF: intrinsic share price (FCFE/Ke), enterprise value (FCFF/WACC),
    and a sensitivity grid. Copy literal numbers from prior tool outputs; never compute.

    Args:
        fcfe, fcff: validated values in crore (run_cashflow_analysis).
        ke, wacc: decimals (calculate_cost_of_capital).
        growth_rate, shares_outstanding, current_price: from financial data.
        terminal_growth_rate: pass 0.0 or omit — the tool selects it; do NOT compute it.
        years: forecast horizon (default 3).

    Returns JSON: intrinsic_share_price, verdict, intrinsic_enterprise_value, sensitivity_analysis.
    """
    return run_skill(_VALUATION_SKILL, {
        "fcfe": fcfe,
        "fcff": fcff,
        "ke": ke,
        "wacc": wacc,
        "growth_rate": growth_rate,
        "shares_outstanding": shares_outstanding,
        "current_price": current_price,
        "terminal_growth_rate": terminal_growth_rate,
        "years": years,
    })


def create_valuation_agent() -> LlmAgent:
    return LlmAgent(
        name="valuation_agent",
        model=LiteLlm(
            model="groq/llama-3.3-70b-versatile",
            api_key=os.environ.get("GROQ_API_KEY"),
            # Cap completion tokens (output is a ~600-token combined JSON). This is
            # the agent that previously broke the 12k tokens-per-minute limit: it
            # can make two tool-call rounds in one window, so keeping each request
            # small (capped reservation + trimmed tool docstrings) lets both fit:
            # worst case ~10.7k tokens/min, comfortably under the 12k limit.
            max_tokens=1200,
        ),
        instruction="""You are a valuation agent. Given financial analysis results and \
market data, calculate the intrinsic value of the company using DCF methodology. \
Always use deterministic tools for all calculations. Never state a valuation verdict \
without running the calculator first.

You have the following financial data:
{temp:financial_data}

You have the following analysis results:
{temp:analysis_results}

Your tasks:

1. Call calculate_cost_of_capital by extracting these individual values from \
{temp:financial_data} and passing them as separate named parameters:
   - beta (decimal, e.g. 0.8)
   - risk_free_rate (decimal, default 0.0685 if missing)
   - market_return (decimal, default 0.12 if missing)
   - interest_expense (raw INR)
   - total_non_current_liabilities (raw INR)
   - shareholders_equity (raw INR)
   - tax_expense (raw INR)
   - pretax_income (raw INR)

2. From the calculate_cost_of_capital result, extract:
   - ke: read the top-level "ke" field. Do NOT default to 0 — if it is missing \
or zero, the tool returned an error; check the result for an "error" key first.
   - wacc: read the top-level "wacc" field. Do NOT default to 0.

3. From {temp:analysis_results}, extract:
   - fcfe = cashflow_analysis → fcfe → validated_fcfe
   - fcff = cashflow_analysis → fcff → validated_fcff
   IMPORTANT: these values are already in INR crore (e.g. 2354.19). \
Pass them directly to run_dcf_valuation without any division or conversion. \
Do NOT multiply or divide by 10,000,000.

4. From {temp:financial_data}, extract:
   - growth_rate (sector growth rate, decimal)
   - shares_outstanding (in crore)
   - current_price (current market price in INR per share)

5. Call run_dcf_valuation with fcfe, fcff, ke, wacc, growth_rate, \
shares_outstanding, current_price, and years=3.
   CRITICAL: Do NOT pass terminal_growth_rate (omit it, or pass 0.0) — the tool \
selects it deterministically. NEVER perform arithmetic in tool arguments: every \
argument value must be a single literal number copied directly from a previous \
tool's output. Do not write expressions like "ke - 0.01" or "0.07 - 0.01" — \
these are invalid and will fail. If a value is not available as a literal number, \
re-read the earlier tool output to find it.

After both tools return, combine their results into one JSON object with keys \
"cost_of_capital" and "dcf_valuation". Output ONLY the combined JSON — no markdown, \
no explanation text.""",
        tools=[calculate_cost_of_capital, run_dcf_valuation],
        output_key="temp:valuation_results",
        include_contents="none",
    )


valuation_agent = create_valuation_agent()
