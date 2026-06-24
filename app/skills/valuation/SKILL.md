---
name: valuation
description: Performs DCF valuation to calculate intrinsic share price and enterprise value. Use when the user asks about intrinsic value, whether a stock is undervalued or overvalued, or requests a DCF analysis.
---

# Valuation Skill

## Goal
Calculate intrinsic share price using DCF and return undervalued/overvalued verdict.

## Instructions
1. Receive FCFE, FCFF, Ke, WACC, growth rate, terminal growth rate, shares outstanding
2. Run scripts/calculate_valuation.py
3. Return intrinsic share price, EV, sensitivity table, and verdict

## Constraints
- Terminal growth rate must be less than cost of equity — raise error otherwise
- Never state a valuation verdict without running the script first
