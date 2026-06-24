---
name: cost-of-capital
description: Calculates WACC, cost of equity via CAPM, and cost of debt. Use when the user asks about discount rate, WACC, cost of equity, or capital structure.
---

# Cost of Capital Skill

## Goal
Calculate WACC and its components from financial data.

## Instructions
1. Receive financial data + market data (beta, risk-free rate)
2. Run scripts/calculate_cost_of_capital.py
3. Return Ke, Kd, Wd, We, WACC

## Constraints
- Risk-free rate should be current 10-year government bond yield
- Always show the CAPM formula breakdown in output
