"""Analysis agent — runs ratio analysis and free cash flow calculations.

The tool functions are thin wrappers that invoke the Agent Skill scripts under
app/skills/ as subprocesses; all deterministic math lives in those scripts.
"""
import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app.agents.tpm_pacer import cooldown_before_agent, mark_llm_activity
from app.skills.runner import run_skill

_RATIO_SKILL = "app/skills/ratio-analysis/scripts/calculate_ratios.py"
_CASHFLOW_SKILL = "app/skills/cashflow-analysis/scripts/calculate_cashflows.py"


def run_ratio_analysis(
    total_assets: float,
    current_assets: float,
    inventory: float,
    cash: float,
    accounts_receivable: float,
    current_liabilities: float,
    total_non_current_liabilities: float,
    shareholders_equity: float,
    total_revenue: float,
    gross_profit: float,
    net_income: float,
    ebit: float,
    interest_expense: float,
    cfo: float,
    current_price: float,
    shares_outstanding: float,
) -> str:
    """Calculate all financial ratios: liquidity, solvency, profitability,
    efficiency, and DuPont decomposition.

    All monetary parameters are raw INR as returned by yfinance.
    current_price is INR per share. shares_outstanding is in crore.

    Returns:
        JSON string with ratio results grouped by category.
    """
    return run_skill(_RATIO_SKILL, {
        "total_assets": total_assets,
        "current_assets": current_assets,
        "inventory": inventory,
        "cash": cash,
        "accounts_receivable": accounts_receivable,
        "current_liabilities": current_liabilities,
        "total_non_current_liabilities": total_non_current_liabilities,
        "shareholders_equity": shareholders_equity,
        "total_revenue": total_revenue,
        "gross_profit": gross_profit,
        "net_income": net_income,
        "ebit": ebit,
        "interest_expense": interest_expense,
        "cfo": cfo,
        "current_price": current_price,
        "shares_outstanding": shares_outstanding,
    })


def run_cashflow_analysis(
    net_income: float,
    non_cash_expenses: float,
    cfo: float,
    capex: float,
    ebit: float,
    interest_expense: float,
    tax_expense: float,
    pretax_income: float,
    increase_in_current_assets: float,
    increase_in_current_liabilities: float,
    net_borrowing: float,
) -> str:
    """Calculate validated FCFF and FCFE using 3 independent methods each.

    All monetary parameters are raw INR as returned by yfinance.

    Returns:
        JSON string with validated FCFF, validated FCFE, all 3 method values,
        and cross_validation status.
    """
    return run_skill(_CASHFLOW_SKILL, {
        "net_income": net_income,
        "non_cash_expenses": non_cash_expenses,
        "cfo": cfo,
        "capex": capex,
        "ebit": ebit,
        "interest_expense": interest_expense,
        "tax_expense": tax_expense,
        "pretax_income": pretax_income,
        "increase_in_current_assets": increase_in_current_assets,
        "increase_in_current_liabilities": increase_in_current_liabilities,
        "net_borrowing": net_borrowing,
    })


def create_analysis_agent() -> LlmAgent:
    return LlmAgent(
        name="analysis_agent",
        model=LiteLlm(
            model="groq/llama-3.3-70b-versatile",
            api_key=os.environ.get("GROQ_API_KEY"),
            # Cap completion tokens (output is a ~700-token combined JSON) so each
            # request stays well under Groq's 12k tokens-per-minute limit.
            max_tokens=1500,
        ),
        instruction="""You are a financial analysis agent. Given financial statement data, \
calculate all financial ratios and free cash flows using the deterministic calculator \
tools. Never calculate any numbers yourself — always use the provided tools.

You have the following financial data:
{temp:financial_data}

Your tasks:

1. Call run_ratio_analysis by extracting these individual numeric values from the JSON \
above and passing them as separate named parameters (all monetary values are raw INR):
   total_assets, current_assets, inventory, cash, accounts_receivable, \
current_liabilities, total_non_current_liabilities, shareholders_equity, \
total_revenue, gross_profit, net_income, ebit, interest_expense, \
cfo, current_price, shares_outstanding

2. Call run_cashflow_analysis by extracting these individual numeric values:
   net_income, non_cash_expenses, cfo, capex, ebit, interest_expense, \
tax_expense, pretax_income, increase_in_current_assets, \
increase_in_current_liabilities, net_borrowing

After both tools return results, combine them into one JSON object with two keys: \
"ratio_analysis" and "cashflow_analysis". Output ONLY the combined JSON — no markdown, \
no explanation text.""",
        tools=[run_ratio_analysis, run_cashflow_analysis],
        output_key="temp:analysis_results",
        include_contents="none",
        # Wait out the TPM window before the first call; timestamp each call after it.
        before_agent_callback=cooldown_before_agent,
        after_model_callback=mark_llm_activity,
    )


analysis_agent = create_analysis_agent()
