#!/usr/bin/env python3
"""
Accepts valuation inputs as JSON via stdin, runs DCF valuation, prints results as JSON.

Output schema matches the run_dcf_valuation tool contract consumed by the report agent.

The terminal growth rate is selected DETERMINISTICALLY here (never by the LLM): pass
terminal_growth_rate = 0.0 (or omit) and the script picks a 0.08 pharma long-run
nominal GDP proxy, backing off to keep the Gordon Growth model defined below BOTH ke
and wacc (so the FCFE/Ke and FCFF/WACC methods are both valid).

Required input keys:
  fcfe                -- base FCFE in crore (from cashflow-analysis skill)
  fcff                -- base FCFF in crore (from cashflow-analysis skill)
  ke                  -- cost of equity as decimal (from cost-of-capital skill)
  wacc                -- WACC as decimal (from cost-of-capital skill)
  growth_rate         -- near-term forecast growth rate (from get_sector_growth_rate)
  shares_outstanding  -- in crore (from get_market_data)
  current_price       -- current market price in INR per share

Optional input keys:
  terminal_growth_rate -- pass 0.0 or omit to let the script select it (recommended)
  years                -- forecast horizon in years (default: 3)
  ke_values            -- list of ke values for the sensitivity grid (default: ±2 steps)
  tg_values            -- list of terminal growth rates for the grid (default: ±1 step)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[4]))

from app.calculators.dcf import DCFCalculator


def _default_ke_values(ke: float) -> list:
    step = 0.005
    return sorted({round(ke + i * step, 4) for i in range(-2, 3)})


def _default_tg_values(tg: float) -> list:
    step = 0.01
    return sorted({round(tg + i * step, 4) for i in range(-1, 2)})


def main():
    data = json.load(sys.stdin)

    try:
        fcfe                 = data["fcfe"]
        fcff                 = data["fcff"]
        ke                   = data["ke"]
        wacc                 = data["wacc"]
        growth_rate          = data["growth_rate"]
        shares_outstanding   = data["shares_outstanding"]
        current_price        = data["current_price"]
        terminal_growth_rate = data.get("terminal_growth_rate", 0.0)
        years                = data.get("years", 3)

        if ke <= 0 or wacc <= 0:
            print(json.dumps({
                "error": f"ke ({ke}) and wacc ({wacc}) must both be positive — "
                         "check the calculate_cost_of_capital output."
            }))
            return

        # --- Deterministic terminal growth selection (never done by the LLM) ---
        # tg must stay below BOTH ke and wacc so the Gordon Growth terminal value
        # is defined for the equity (FCFE/Ke) and enterprise (FCFF/WACC) methods.
        floor_rate = min(ke, wacc)
        if terminal_growth_rate <= 0.0:
            terminal_growth_rate = 0.08  # pharma long-run nominal GDP proxy
        if terminal_growth_rate >= floor_rate:
            terminal_growth_rate = round(floor_rate - 0.01, 4)
        if terminal_growth_rate <= 0 or terminal_growth_rate >= floor_rate:
            print(json.dumps({
                "error": f"Cannot select a valid terminal growth rate below "
                         f"min(ke={ke}, wacc={wacc}); rates are too low for the model."
            }))
            return

        ke_values = data.get("ke_values") or _default_ke_values(ke)
        tg_values = data.get("tg_values") or _default_tg_values(terminal_growth_rate)

        calc = DCFCalculator()

        # --- Equity value (FCFE / Ke) ---
        forecasted_fcfe  = calc.forecast_cashflows(fcfe, growth_rate, years)
        equity_value     = calc.intrinsic_equity_value(forecasted_fcfe, ke, terminal_growth_rate)
        share_price      = calc.intrinsic_share_price(equity_value, shares_outstanding)
        verdict          = calc.valuation_verdict(share_price, current_price)

        # --- Enterprise value (FCFF / WACC) ---
        forecasted_fcff  = calc.forecast_cashflows(fcff, growth_rate, years)
        enterprise_value = calc.intrinsic_enterprise_value(forecasted_fcff, wacc, terminal_growth_rate)

        # --- Sensitivity analysis ---
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

        print(json.dumps({
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
        }, indent=2))

    except Exception as exc:
        print(json.dumps({"error": f"DCF valuation failed: {exc}"}))


if __name__ == "__main__":
    main()
