"""Valuation agent — computes WACC, cost of equity, DCF intrinsic value, and verdict.

The single tool function chains the Agent Skill scripts under app/skills/ as
subprocesses; all deterministic math lives in those scripts. Cost-of-capital and
the DCF are exposed as ONE tool because the DCF strictly depends on the
cost-of-capital output (Ke, WACC). Splitting them into two tools let the model
fire both in parallel, so the DCF ran with Ke=WACC=0, errored, and the model
retried both — a double round-trip that blew the Groq 12k tokens-per-minute
limit. Folding them into one call removes the ordering race and keeps the agent
to a single LLM round.
"""
import json
import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app.agents.tpm_pacer import cooldown_before_agent, mark_llm_activity
from app.skills.runner import run_skill

_COST_OF_CAPITAL_SKILL = "app/skills/cost-of-capital/scripts/calculate_cost_of_capital.py"
_VALUATION_SKILL = "app/skills/valuation/scripts/calculate_valuation.py"


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
    """Compute cost of capital (CAPM) then the DCF valuation in one deterministic step.

    This single call runs the cost-of-capital skill first, then feeds its Ke and
    WACC into the DCF skill — you never pass Ke or WACC yourself. Every argument
    must be a single literal number copied from {temp:financial_data} or
    {temp:analysis_results}; never perform arithmetic in arguments.

    Args:
        beta, risk_free_rate, market_return: decimals (defaults 0.0685 / 0.12 if missing).
        interest_expense, total_non_current_liabilities, shareholders_equity,
            tax_expense, pretax_income: raw INR from financial data.
        fcfe, fcff: validated values already in INR crore (run_cashflow_analysis) —
            pass directly, do NOT multiply or divide by 10,000,000.
        growth_rate: sector growth rate (decimal).
        shares_outstanding: in crore.
        current_price: current market price in INR per share.
        years: forecast horizon (default 3).

    Returns:
        JSON string {"cost_of_capital": {...}, "dcf_valuation": {...}}, or
        {"error": "..."} if cost of capital could not be computed.
    """
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
        return json.dumps({
            "error": f"cost of capital returned non-positive ke ({ke}) / wacc ({wacc})"
        })

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


def create_valuation_agent() -> LlmAgent:
    return LlmAgent(
        name="valuation_agent",
        model=LiteLlm(
            model="groq/llama-3.3-70b-versatile",
            api_key=os.environ.get("GROQ_API_KEY"),
            # Cap completion tokens (output is a ~600-token combined JSON). The DCF
            # depends on the cost-of-capital output, so both run inside ONE tool
            # (run_valuation) and the agent makes a single LLM round — well under
            # the Groq 12k tokens-per-minute limit. Disable parallel tool calls as
            # belt-and-suspenders against any extra round-trip.
            max_tokens=1200,
            parallel_tool_calls=False,
        ),
        instruction="""You are a valuation agent. Given financial analysis results and \
market data, calculate the intrinsic value of the company using DCF methodology. \
Always use the deterministic tool for all calculations. Never state a valuation verdict \
without running the tool first.

You have the following financial data:
{temp:financial_data}

You have the following analysis results:
{temp:analysis_results}

Call run_valuation EXACTLY ONCE with these arguments, each a single literal number \
copied from the data above (never compute or transform a value in an argument):

From {temp:financial_data}:
   - beta (decimal, e.g. 0.8)
   - risk_free_rate (decimal, default 0.0685 if missing)
   - market_return (decimal, default 0.12 if missing)
   - interest_expense (raw INR)
   - total_non_current_liabilities (raw INR)
   - shareholders_equity (raw INR)
   - tax_expense (raw INR)
   - pretax_income (raw INR)
   - growth_rate (sector growth rate, decimal)
   - shares_outstanding (in crore)
   - current_price (current market price in INR per share)

From {temp:analysis_results}:
   - fcfe = cashflow_analysis → fcfe → validated_fcfe
   - fcff = cashflow_analysis → fcff → validated_fcff
   IMPORTANT: fcfe and fcff are already in INR crore (e.g. 2354.19). Pass them \
directly — do NOT multiply or divide by 10,000,000.

Pass years=3. Do NOT pass Ke, WACC, or terminal_growth_rate — the tool computes \
cost of capital internally and feeds it into the DCF for you.

The tool returns one JSON object with keys "cost_of_capital" and "dcf_valuation". \
Output that JSON object verbatim — no markdown, no explanation text.""",
        tools=[run_valuation],
        output_key="temp:valuation_results",
        include_contents="none",
        # Wait out the TPM window before the first call; timestamp each call after it.
        before_agent_callback=cooldown_before_agent,
        after_model_callback=mark_llm_activity,
    )


valuation_agent = create_valuation_agent()
