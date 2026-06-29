"""Valuation agent — computes WACC, cost of equity, DCF intrinsic value, and verdict."""
import json
import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app.calculators.cost_of_capital import CostOfCapitalCalculator
from app.calculators.dcf import DCFCalculator

_CRORE = 10_000_000


def _c(value):
    return value / _CRORE if value is not None else None


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
    try:
        ie  = _c(interest_expense)
        ltd = _c(total_non_current_liabilities)
        eq  = _c(shareholders_equity)
        te  = _c(tax_expense)
        pi  = _c(pretax_income)

        if pi == 0:
            return json.dumps({"error": "pretax_income is zero — cannot compute tax rate"})
        if not ltd or ltd == 0:
            return json.dumps({"error": "total_non_current_liabilities is zero — cannot compute cost of debt"})

        tax_rate   = te / pi
        pre_tax_kd = ie / ltd

        calc = CostOfCapitalCalculator()

        ke   = calc.capm_cost_of_equity(risk_free_rate, beta, market_return)
        kd   = calc.post_tax_cost_of_debt(pre_tax_kd, tax_rate)
        wd   = calc.weight_of_debt(ltd, eq)
        we   = calc.weight_of_equity(ltd, eq)
        wacc = calc.wacc(wd, kd, we, ke)

        return json.dumps({
            "tool": "calculate_cost_of_capital",
            "capm_breakdown": {
                "formula":             "Ke = Rf + Beta × (Rm - Rf)",
                "risk_free_rate":      risk_free_rate,
                "beta":                beta,
                "market_return":       market_return,
                "equity_risk_premium": round(market_return - risk_free_rate, 6),
                "ke":                  ke,
            },
            "cost_of_debt": {
                "pre_tax_kd":  round(pre_tax_kd, 6),
                "tax_rate":    round(tax_rate, 6),
                "post_tax_kd": kd,
            },
            "weights": {
                "wd": round(wd, 6),
                "we": round(we, 6),
            },
            "wacc": {
                "formula": "WACC = (Wd × Kd) + (We × Ke)",
                "wacc":    wacc,
            },
            "ke":   ke,
            "kd":   kd,
            "wacc": wacc,
        }, indent=2)

    except Exception as exc:
        return json.dumps({"error": f"Cost of capital calculation failed: {exc}"})


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
    try:
        if ke <= 0 or wacc <= 0:
            return json.dumps({
                "error": f"ke ({ke}) and wacc ({wacc}) must both be positive — "
                         "check the calculate_cost_of_capital output."
            })

        # --- Deterministic terminal growth selection (never done by the LLM) ---
        # tg must stay below BOTH ke and wacc so the Gordon Growth terminal value
        # is defined for the equity (FCFE/Ke) and enterprise (FCFF/WACC) methods.
        floor_rate = min(ke, wacc)
        if terminal_growth_rate <= 0.0:
            terminal_growth_rate = 0.08  # pharma long-run nominal GDP proxy
        if terminal_growth_rate >= floor_rate:
            terminal_growth_rate = round(floor_rate - 0.01, 4)
        if terminal_growth_rate <= 0 or terminal_growth_rate >= floor_rate:
            return json.dumps({
                "error": f"Cannot select a valid terminal growth rate below "
                         f"min(ke={ke}, wacc={wacc}); rates are too low for the model."
            })

        calc = DCFCalculator()

        def _default_ke_values(k: float):
            step = 0.005
            return sorted({round(k + i * step, 4) for i in range(-2, 3)})

        def _default_tg_values(tg: float):
            step = 0.01
            return sorted({round(tg + i * step, 4) for i in range(-1, 2)})

        ke_values = _default_ke_values(ke)
        tg_values = _default_tg_values(terminal_growth_rate)

        forecasted_fcfe  = calc.forecast_cashflows(fcfe, growth_rate, years)
        equity_value     = calc.intrinsic_equity_value(forecasted_fcfe, ke, terminal_growth_rate)
        share_price      = calc.intrinsic_share_price(equity_value, shares_outstanding)
        verdict          = calc.valuation_verdict(share_price, current_price)

        forecasted_fcff  = calc.forecast_cashflows(fcff, growth_rate, years)
        enterprise_value = calc.intrinsic_enterprise_value(forecasted_fcff, wacc, terminal_growth_rate)

        sensitivity = calc.sensitivity_analysis(
            base_fcfe=fcfe,
            ke_values=ke_values,
            tg_values=tg_values,
            shares_outstanding=shares_outstanding,
            growth_rate=growth_rate,
            years=years,
        )
        sensitivity_str = {
            str(k): {str(tg): v for tg, v in row.items()}
            for k, row in sensitivity.items()
        }

        return json.dumps({
            "tool": "run_dcf_valuation",
            "inputs": {
                "fcfe":                 round(fcfe, 2),
                "fcff":                 round(fcff, 2),
                "ke":                   ke,
                "wacc":                 wacc,
                "growth_rate":          growth_rate,
                "terminal_growth_rate": terminal_growth_rate,
                "shares_outstanding":   shares_outstanding,
                "years":                years,
            },
            "equity_valuation": {
                "forecasted_fcfe":        [round(v, 2) for v in forecasted_fcfe],
                "intrinsic_equity_value": round(equity_value, 2),
                "intrinsic_share_price":  share_price,
                "current_market_price":   current_price,
                "verdict":                verdict,
            },
            "enterprise_valuation": {
                "forecasted_fcff":            [round(v, 2) for v in forecasted_fcff],
                "intrinsic_enterprise_value": round(enterprise_value, 2),
            },
            "sensitivity_analysis": sensitivity_str,
        }, indent=2)

    except Exception as exc:
        return json.dumps({"error": f"DCF valuation failed: {exc}"})


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
