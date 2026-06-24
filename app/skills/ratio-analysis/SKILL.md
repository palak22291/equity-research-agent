---
name: ratio-analysis
description: Calculates financial ratios for a company including liquidity, profitability, efficiency, solvency and valuation ratios. Use when the user asks to analyze ratios, financial health, or performance metrics of a company.
---

# Ratio Analysis Skill

## Goal
Calculate all financial ratios from a company's financial statements.

## Instructions
1. Receive financial statement data as a Python dict
2. Run scripts/calculate_ratios.py with the data
3. Return structured ratio results grouped by category

## Constraints
- NEVER calculate ratios manually in text — always delegate to the script
- If any required input is missing, report which field is missing
- Round all outputs to 2 decimal places
