"""Analysis agent — runs ratio analysis and free cash flow calculations."""
import json
import os

from google.adk.agents import LlmAgent

from app.calculators.cashflows import CashFlowCalculator
from app.calculators.ratios import RatioCalculator

_CRORE = 10_000_000


def _c(value):
    """Convert raw INR to crore. Returns None if value is None."""
    return value / _CRORE if value is not None else None


def _parse_json(raw: str) -> dict:
    """Parse JSON, stripping markdown code fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    return json.loads(text)


def run_ratio_analysis(financial_data_json: str) -> str:
    """Calculate all financial ratios: liquidity, solvency, profitability,
    efficiency, and DuPont decomposition.

    Args:
        financial_data_json: JSON string from fetch_all_financial_data containing
            all balance sheet and income statement fields in raw INR.

    Returns:
        JSON string with ratio results grouped by category.
    """
    try:
        d = _parse_json(financial_data_json)
    except (json.JSONDecodeError, ValueError) as exc:
        return json.dumps({"error": f"Failed to parse financial_data_json: {exc}"})

    try:
        current_assets      = _c(d["current_assets"])
        current_liabilities = _c(d["current_liabilities"])
        cash                = _c(d["cash"])
        accounts_receivable = _c(d["accounts_receivable"])
        inventory           = _c(d["inventory"])
        total_assets        = _c(d["total_assets"])
        long_term_debt      = _c(d["total_non_current_liabilities"])
        shareholders_equity = _c(d["shareholders_equity"])
        total_revenue       = _c(d["total_revenue"])
        gross_profit        = _c(d["gross_profit"])
        net_income          = _c(d["net_income"])
        ebit                = _c(d["ebit"])
        interest_expense    = _c(d["interest_expense"])
        non_cash_expenses   = _c(d.get("non_cash_expenses"))
        current_price       = d.get("current_price")
        shares_outstanding  = d.get("shares_outstanding")

        cogs             = total_revenue - gross_profit
        fixed_assets     = total_assets - current_assets
        total_liabilities = current_liabilities + long_term_debt

        c = RatioCalculator()

        npm = c.net_profit_margin(net_income, total_revenue)
        at  = c.asset_turnover(total_revenue, total_assets)
        em  = round(total_assets / shareholders_equity, 6) if shareholders_equity else None

        result = {
            "tool": "run_ratio_analysis",
            "company": d.get("company_name", ""),
            "fiscal_year_end": d.get("fiscal_year_end", ""),
            "liquidity": {
                "current_ratio": c.current_ratio(current_assets, current_liabilities),
                "quick_ratio":   c.quick_ratio(cash, accounts_receivable, current_liabilities),
                "cash_ratio":    c.cash_ratio(cash, current_liabilities),
            },
            "solvency": {
                "debt_to_equity":    c.debt_to_equity(current_liabilities, long_term_debt, shareholders_equity),
                "interest_coverage": c.interest_coverage(ebit, interest_expense),
                "debt_to_assets":    c.debt_to_assets(total_liabilities, total_assets),
            },
            "profitability": {
                "gross_profit_margin": c.gross_profit_margin(gross_profit, total_revenue),
                "ebit_margin":         c.ebit_margin(ebit, total_revenue),
                "ebitda_margin": (
                    c.ebitda_margin(ebit + non_cash_expenses, total_revenue)
                    if non_cash_expenses is not None else None
                ),
                "net_profit_margin":   npm,
                "return_on_equity":    c.return_on_equity(net_income, shareholders_equity),
                "return_on_assets":    c.return_on_assets(net_income, total_assets),
                "roce":                c.roce(ebit, shareholders_equity, total_liabilities),
            },
            "efficiency": {
                "asset_turnover":         at,
                "inventory_turnover":     c.inventory_turnover(cogs, inventory),
                "receivables_turnover":   c.receivables_turnover(total_revenue, accounts_receivable),
                "fixed_asset_turnover":   c.fixed_asset_turnover(total_revenue, fixed_assets),
                "days_sales_outstanding": c.days_sales_outstanding(accounts_receivable, total_revenue),
            },
            "dupont": {
                "net_profit_margin": npm,
                "asset_turnover":    at,
                "equity_multiplier": round(em, 2) if em is not None else None,
                "roe":               c.dupont_roe(npm, at, em) if em is not None else None,
            },
        }

        if current_price is not None and shares_outstanding is not None:
            eps_val = c.eps(net_income, shares_outstanding)
            result["valuation_multiples"] = {
                "eps":      eps_val,
                "pe_ratio": c.pe_ratio(current_price, eps_val),
            }

        return json.dumps(result, indent=2)

    except Exception as exc:
        return json.dumps({"error": f"Ratio analysis failed: {exc}"})


def run_cashflow_analysis(financial_data_json: str) -> str:
    """Calculate validated FCFF and FCFE using 3 independent methods each.
    Cross-validates that all 3 methods agree within tolerance.

    Args:
        financial_data_json: JSON string from fetch_all_financial_data.
            Must include increase_in_current_assets, increase_in_current_liabilities,
            and net_borrowing (year-over-year balance sheet deltas).

    Returns:
        JSON string with validated FCFF, validated FCFE, all 3 method values,
        and cross_validation status.
    """
    try:
        d = _parse_json(financial_data_json)
    except (json.JSONDecodeError, ValueError) as exc:
        return json.dumps({"error": f"Failed to parse financial_data_json: {exc}"})

    required_delta_fields = [
        "increase_in_current_assets",
        "increase_in_current_liabilities",
        "net_borrowing",
    ]
    missing = [f for f in required_delta_fields if d.get(f) is None]
    if missing:
        return json.dumps({
            "error": (
                f"Missing required delta fields for cashflow analysis: {missing}. "
                "Ensure fetch_all_financial_data was called with a ticker that has "
                "at least 2 years of balance sheet history."
            )
        })

    try:
        net_income    = _c(d["net_income"])
        non_cash_exp  = _c(d["non_cash_expenses"])
        cfo           = _c(d["cfo"])
        capex         = _c(d["capex"])
        ebit          = _c(d["ebit"])
        interest      = _c(d["interest_expense"])
        tax_expense   = _c(d["tax_expense"])
        pretax_income = _c(d["pretax_income"])
        delta_ca      = _c(d["increase_in_current_assets"])
        delta_cl      = _c(d["increase_in_current_liabilities"])
        net_borrowing = _c(d["net_borrowing"])

        if pretax_income == 0:
            return json.dumps({"error": "pretax_income is zero — cannot compute tax rate"})
        tax_rate = tax_expense / pretax_income

        calc = CashFlowCalculator()

        try:
            fcff = calc.validated_fcff(
                net_income=net_income,
                non_cash_expenses=non_cash_exp,
                increase_in_current_assets=delta_ca,
                increase_in_current_liabilities=delta_cl,
                interest=interest,
                tax_rate=tax_rate,
                capex=capex,
                cfo=cfo,
                ebit=ebit,
                tolerance=2.0,
            )
        except ValueError as exc:
            return json.dumps({"error": f"FCFF cross-validation failed: {exc}"})

        try:
            fcfe = calc.validated_fcfe(
                net_income=net_income,
                non_cash_expenses=non_cash_exp,
                increase_in_current_assets=delta_ca,
                increase_in_current_liabilities=delta_cl,
                interest=interest,
                tax_rate=tax_rate,
                capex=capex,
                cfo=cfo,
                ebit=ebit,
                ocf=cfo,
                net_borrowing=net_borrowing,
                tolerance=2.0,
            )
        except ValueError as exc:
            return json.dumps({"error": f"FCFE cross-validation failed: {exc}"})

        nopat = calc.nopat(ebit, tax_rate)

        return json.dumps({
            "tool": "run_cashflow_analysis",
            "inputs": {
                "net_income":                      round(net_income, 2),
                "non_cash_expenses":               round(non_cash_exp, 2),
                "cfo":                             round(cfo, 2),
                "capex":                           round(capex, 2),
                "tax_rate":                        round(tax_rate, 6),
                "increase_in_current_assets":      round(delta_ca, 2),
                "increase_in_current_liabilities": round(delta_cl, 2),
                "net_borrowing":                   round(net_borrowing, 2),
            },
            "fcff": {
                "method_1_net_income": round(calc.fcff_from_net_income(
                    net_income, non_cash_exp, delta_ca, delta_cl, interest, tax_rate, capex
                ), 2),
                "method_2_nopat": round(calc.fcff_from_nopat(
                    nopat, non_cash_exp, delta_ca, delta_cl, capex
                ), 2),
                "method_3_cfo": round(calc.fcff_from_cfo(cfo, interest, tax_rate, capex), 2),
                "validated_fcff": round(fcff, 2),
            },
            "fcfe": {
                "method_1_net_income": round(calc.fcfe_from_net_income(
                    net_income, non_cash_exp, delta_ca, delta_cl, capex, net_borrowing
                ), 2),
                "method_2_fcff": round(calc.fcfe_from_fcff(fcff, interest, tax_rate, net_borrowing), 2),
                "method_3_ocf":  round(calc.fcfe_from_ocf(cfo, capex, net_borrowing), 2),
                "validated_fcfe": round(fcfe, 2),
            },
            "cross_validation": "passed",
        }, indent=2)

    except Exception as exc:
        return json.dumps({"error": f"Cashflow analysis failed: {exc}"})


analysis_agent = LlmAgent(
    name="analysis_agent",
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    instruction="""You are a financial analysis agent. Given financial statement data, \
calculate all financial ratios and free cash flows using the deterministic calculator \
tools. Never calculate any numbers yourself — always use the provided tools.

You have the following financial data from the data agent:
{financial_data}

Your tasks:
1. Call run_ratio_analysis with the financial_data_json set to the JSON content above.
2. Call run_cashflow_analysis with the financial_data_json set to the JSON content above.

After both tools return results, combine them into one JSON object with two keys: \
"ratio_analysis" and "cashflow_analysis". Output ONLY the combined JSON — no markdown, \
no explanation text.""",
    tools=[run_ratio_analysis, run_cashflow_analysis],
    output_key="analysis_results",
    include_contents="none",
)
