"""Analysis agent — runs ratio analysis and free cash flow calculations."""
import json
import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app.calculators.cashflows import CashFlowCalculator
from app.calculators.ratios import RatioCalculator

_CRORE = 10_000_000


def _c(value):
    """Convert raw INR to crore. Returns None if value is None."""
    return value / _CRORE if value is not None else None


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
) -> dict:
    """Calculate all financial ratios: liquidity, solvency, profitability,
    efficiency, and DuPont decomposition.

    All monetary parameters are raw INR as returned by yfinance.
    current_price is INR per share. shares_outstanding is in crore.

    Returns:
        JSON string with ratio results grouped by category.
    """
    try:
        ca  = _c(current_assets)
        cl  = _c(current_liabilities)
        ch  = _c(cash)
        ar  = _c(accounts_receivable)
        inv = _c(inventory)
        ta  = _c(total_assets)
        ltd = _c(total_non_current_liabilities)
        eq  = _c(shareholders_equity)
        rev = _c(total_revenue)
        gp  = _c(gross_profit)
        ni  = _c(net_income)
        eb  = _c(ebit)
        ie  = _c(interest_expense)

        cogs         = rev - gp
        fixed_assets = ta - ca
        total_liab   = cl + ltd

        r = RatioCalculator()

        npm = r.net_profit_margin(ni, rev)
        at  = r.asset_turnover(rev, ta)
        em  = round(ta / eq, 6) if eq else None

        result = {
            "tool": "run_ratio_analysis",
            "liquidity": {
                "current_ratio": r.current_ratio(ca, cl),
                "quick_ratio":   r.quick_ratio(ch, ar, cl),
                "cash_ratio":    r.cash_ratio(ch, cl),
            },
            "solvency": {
                "debt_to_equity":    r.debt_to_equity(cl, ltd, eq),
                "interest_coverage": r.interest_coverage(eb, ie),
                "debt_to_assets":    r.debt_to_assets(total_liab, ta),
            },
            "profitability": {
                "gross_profit_margin": r.gross_profit_margin(gp, rev),
                "ebit_margin":         r.ebit_margin(eb, rev),
                "net_profit_margin":   npm,
                "return_on_equity":    r.return_on_equity(ni, eq),
                "return_on_assets":    r.return_on_assets(ni, ta),
                "roce":                r.roce(eb, eq, total_liab),
            },
            "efficiency": {
                "asset_turnover":         at,
                "inventory_turnover":     r.inventory_turnover(cogs, inv),
                "receivables_turnover":   r.receivables_turnover(rev, ar),
                "fixed_asset_turnover":   r.fixed_asset_turnover(rev, fixed_assets),
                "days_sales_outstanding": r.days_sales_outstanding(ar, rev),
            },
            "dupont": {
                "net_profit_margin": npm,
                "asset_turnover":    at,
                "equity_multiplier": round(em, 2) if em is not None else None,
                "roe":               r.dupont_roe(npm, at, em) if em is not None else None,
            },
        }

        if current_price is not None and shares_outstanding is not None:
            eps_val = r.eps(ni, shares_outstanding)
            result["valuation_multiples"] = {
                "eps":      eps_val,
                "pe_ratio": r.pe_ratio(current_price, eps_val),
            }

        return json.dumps(result, indent=2)

    except Exception as exc:
        return json.dumps({"error": f"Ratio analysis failed: {exc}"})


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
) -> dict:
    """Calculate validated FCFF and FCFE using 3 independent methods each.

    All monetary parameters are raw INR as returned by yfinance.

    Returns:
        JSON string with validated FCFF, validated FCFE, all 3 method values,
        and cross_validation status.
    """
    try:
        ni      = _c(net_income)
        nce     = _c(non_cash_expenses)
        cfo_c   = _c(cfo)
        capex_c = _c(capex)
        eb      = _c(ebit)
        ie      = _c(interest_expense)
        te      = _c(tax_expense)
        pi      = _c(pretax_income)
        dca     = _c(increase_in_current_assets)
        dcl     = _c(increase_in_current_liabilities)
        nb      = _c(net_borrowing)

        if pi == 0:
            return json.dumps({"error": "pretax_income is zero — cannot compute tax rate"})
        tax_rate = te / pi

        calc = CashFlowCalculator()

        try:
            fcff = calc.validated_fcff(
                net_income=ni,
                non_cash_expenses=nce,
                increase_in_current_assets=dca,
                increase_in_current_liabilities=dcl,
                interest=ie,
                tax_rate=tax_rate,
                capex=capex_c,
                cfo=cfo_c,
                ebit=eb,
                tolerance=500.0,
            )
        except ValueError as exc:
            return json.dumps({"error": f"FCFF cross-validation failed: {exc}"})

        try:
            fcfe = calc.validated_fcfe(
                net_income=ni,
                non_cash_expenses=nce,
                increase_in_current_assets=dca,
                increase_in_current_liabilities=dcl,
                interest=ie,
                tax_rate=tax_rate,
                capex=capex_c,
                cfo=cfo_c,
                ebit=eb,
                ocf=cfo_c,
                net_borrowing=nb,
                tolerance=500.0,
            )
        except ValueError as exc:
            return json.dumps({"error": f"FCFE cross-validation failed: {exc}"})

        nopat = calc.nopat(eb, tax_rate)

        return json.dumps({
            "tool": "run_cashflow_analysis",
            "inputs": {
                "net_income":                      round(ni, 2),
                "non_cash_expenses":               round(nce, 2),
                "cfo":                             round(cfo_c, 2),
                "capex":                           round(capex_c, 2),
                "tax_rate":                        round(tax_rate, 6),
                "increase_in_current_assets":      round(dca, 2),
                "increase_in_current_liabilities": round(dcl, 2),
                "net_borrowing":                   round(nb, 2),
            },
            "fcff": {
                "method_1_net_income": round(calc.fcff_from_net_income(
                    ni, nce, dca, dcl, ie, tax_rate, capex_c
                ), 2),
                "method_2_nopat": round(calc.fcff_from_nopat(
                    nopat, nce, dca, dcl, capex_c
                ), 2),
                "method_3_cfo": round(calc.fcff_from_cfo(cfo_c, ie, tax_rate, capex_c), 2),
                "validated_fcff": round(fcff, 2),
            },
            "fcfe": {
                "method_1_net_income": round(calc.fcfe_from_net_income(
                    ni, nce, dca, dcl, capex_c, nb
                ), 2),
                "method_2_fcff": round(calc.fcfe_from_fcff(fcff, ie, tax_rate, nb), 2),
                "method_3_ocf":  round(calc.fcfe_from_ocf(cfo_c, capex_c, nb), 2),
                "validated_fcfe": round(fcfe, 2),
            },
            "cross_validation": "passed",
        }, indent=2)

    except Exception as exc:
        return json.dumps({"error": f"Cashflow analysis failed: {exc}"})


def create_analysis_agent() -> LlmAgent:
    return LlmAgent(
        name="analysis_agent",
        model=LiteLlm(
            model="groq/llama-3.3-70b-versatile",
            api_key=os.environ.get("GROQ_API_KEY"),
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
    )


analysis_agent = create_analysis_agent()
