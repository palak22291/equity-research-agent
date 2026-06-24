---
name: cashflow-analysis
description: Calculates FCFF and FCFE using three cross-validating methods each. Use when the user asks about free cash flow, cash generation, or wants to verify cash flow consistency.
---

# Cash Flow Analysis Skill

## Goal
Calculate FCFF and FCFE using 3 methods each and cross-validate results.

## Instructions
1. Receive financial statement data
2. Run scripts/calculate_cashflows.py
3. If all 3 methods agree → return validated FCFF and FCFE
4. If methods disagree → flag data inconsistency error

## Constraints
- Always run all 3 methods — never shortcut to just one
- Cross-validation is mandatory per project spec
