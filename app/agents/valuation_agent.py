"""Valuation agent — computes WACC, cost of equity, DCF intrinsic value, and verdict."""
import json
import os
import statistics

from google.adk.agents import LlmAgent

from app.calculators.cost_of_capital import CostOfCapitalCalculator
from app.calculators.dcf import DCFCalculator

_CRORE = 10_000_000


def _c(value):
    return value / _CRORE if value is not None else None


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    return json.loads(text)


def calculate_cost_of_capital(financial_data_json: str) -> str:
    """Compute WACC, cost of equity (Ke), and cost of debt (Kd) using CAPM.

    Uses the book-value weights from the current fiscal year.
    Risk-free rate and market return are read from the financial data
    (defaulting to Indian market assumptions: Rf=6.85%, Rm=12%).

    Args:
        financial_data_json: JSON string from fetch_all_financial_data.
            Required fields: interest_expense, total_non_current_liabilities,
            shareholders_equity, tax_expense, pretax_income, beta,
            risk_free_rate, market_return.

    Returns:
        JSON string with ke, kd (post-tax), wacc, weights, and CAPM breakdown.
    """
    try:
        d = _parse_json(financial_data_json)
    except (json.JSONDecodeError, ValueError) as exc:
        return json.dumps({"error": f"Failed to parse financial_data_json: {exc}"})

    try:
        interest_expense  = _c(d["interest_expense"])
        book_value_debt   = _c(d["total_non_current_liabilities"])
        book_value_equity = _c(d["shareholders_equity"])
        tax_expense       = _c(d["tax_expense"])
        pretax_income     = _c(d["pretax_income"])
        risk_free_rate    = float(d.get("risk_free_rate", 0.0685))
        beta              = float(d["beta"])
        market_return     = float(d.get("market_return", 0.12))

        if pretax_income == 0:
            return json.dumps({"error": "pretax_income is zero — cannot compute tax rate"})
        if not book_value_debt or book_value_debt == 0:
            return json.dumps({"error": "book_value_debt is zero — cannot compute cost of debt"})

        tax_rate    = tax_expense / pretax_income
        pre_tax_kd  = interest_expense / book_value_debt

        calc = CostOfCapitalCalculator()

        ke = calc.capm_cost_of_equity(risk_free_rate, beta, market_return)
        kd = calc.post_tax_cost_of_debt(pre_tax_kd, tax_rate)
        wd = calc.weight_of_debt(book_value_debt, book_value_equity)
        we = calc.weight_of_equity(book_value_debt, book_value_equity)
        wacc = calc.wacc(wd, kd, we, ke)

        return json.dumps({
            "tool": "calculate_cost_of_capital",
            "capm_breakdown": {
                "formula":            "Ke = Rf + Beta × (Rm - Rf)",
                "risk_free_rate":     risk_free_rate,
                "beta":               beta,
                "market_return":      market_return,
                "equity_risk_premium": round(market_return - risk_free_rate, 6),
                "ke":                 ke,
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
    terminal_growth_rate: float = 0.065,
    years: int = 3,
) -> str:
    """Run DCF valuation: compute intrinsic share price (FCFE/Ke method),
    intrinsic enterprise value (FCFF/WACC method), and a sensitivity analysis grid.

    Args:
        fcfe: Validated FCFE in crore (from run_cashflow_analysis).
        fcff: Validated FCFF in crore (from run_cashflow_analysis).
        ke: Cost of equity as decimal (from calculate_cost_of_capital).
        wacc: WACC as decimal (from calculate_cost_of_capital).
        growth_rate: Near-term sector growth rate as decimal (from financial data).
        shares_outstanding: Shares outstanding in crore (from financial data).
        current_price: Current market price in INR per share (from financial data).
        terminal_growth_rate: Long-run nominal GDP growth rate (default: 0.065 for India).
        years: Forecast horizon in years (default: 3).

    Returns:
        JSON string with intrinsic_share_price, verdict (Undervalued/Fairly Valued/
        Overvalued), intrinsic_enterprise_value, and sensitivity_analysis grid.
    """
    try:
        if ke <= terminal_growth_rate:
            return json.dumps({
                "error": (
                    f"terminal_growth_rate ({terminal_growth_rate}) must be less than "
                    f"ke ({ke}) — Gordon Growth model is undefined."
                )
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
                "forecasted_fcfe":       [round(v, 2) for v in forecasted_fcfe],
                "intrinsic_equity_value": round(equity_value, 2),
                "intrinsic_share_price":  share_price,
                "current_market_price":   current_price,
                "verdict":                verdict,
            },
            "enterprise_valuation": {
                "forecasted_fcff":           [round(v, 2) for v in forecasted_fcff],
                "intrinsic_enterprise_value": round(enterprise_value, 2),
            },
            "sensitivity_analysis": sensitivity_str,
        }, indent=2)

    except Exception as exc:
        return json.dumps({"error": f"DCF valuation failed: {exc}"})


valuation_agent = LlmAgent(
    name="valuation_agent",
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    instruction="""You are a valuation agent. Given financial analysis results and \
market data, calculate the intrinsic value of the company using DCF methodology. \
Always use deterministic tools for all calculations. Never state a valuation verdict \
without running the calculator first.

You have the following financial data:
{temp:financial_data}

You have the following analysis results:
{temp:analysis_results}

Your tasks:
1. Call calculate_cost_of_capital with financial_data_json set to the JSON from \
{temp:financial_data} to get ke and wacc.

2. Extract from {temp:analysis_results}:
   - fcfe = the "validated_fcfe" value from the "fcfe" section of "cashflow_analysis"
   - fcff = the "validated_fcff" value from the "fcff" section of "cashflow_analysis"

3. Extract from {temp:financial_data}:
   - growth_rate (sector growth rate)
   - shares_outstanding (in crore)
   - current_price (current market price in INR)

4. Call run_dcf_valuation with fcfe, fcff, ke, wacc, growth_rate, shares_outstanding, \
current_price, and terminal_growth_rate=0.065.

After both tools return, combine their results into one JSON object with keys \
"cost_of_capital" and "dcf_valuation". Output ONLY the combined JSON — no markdown, \
no explanation text.""",
    tools=[calculate_cost_of_capital, run_dcf_valuation],
    output_key="temp:valuation_results",
    include_contents="none",
)
