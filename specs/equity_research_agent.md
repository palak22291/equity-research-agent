# Equity Research Analyst Agent — Spec

## 1. Purpose

Given a company's financial statement data, produce a full equity research
report: liquidity/efficiency/profitability/solvency ratios, FCFF, FCFE,
WACC, DCF-based intrinsic valuation (both Equity Value and Enterprise
Value methods), sensitivity analysis, and a final
undervalued/fairly-valued/overvalued verdict versus current market price.

The agent is **generic**: it must work for any company given properly
structured financial inputs, not just the verified test case (Cipla).

## 2. Ground Truth / Test Case

Cipla Ltd., FY2022–FY2025 data, sourced from a professor-graded (full marks)
academic equity research project. This is the known-correct reference used
to unit-test every calculator before it's trusted in the agent pipeline.

Key verified outputs for Cipla (as on 31-Mar-2025):
- WACC: 8.40%
- Cost of Equity (Ke): 8.44%
- Intrinsic Share Price (FCFE/Ke method): ₹4934.01
- Current Market Price: ₹1441
- Verdict: **Undervalued**
- Intrinsic Enterprise Value (FCFF/WACC method): ₹461,268.36 (in given units)

## 3. Core Calculations (Deterministic — NOT LLM-computed)

### 3.1 Ratios
- Liquidity ratios (e.g., current ratio, quick ratio)
- Efficiency / Activity ratios
- Profitability ratios
- Solvency ratios
- DuPont decomposition

### 3.2 Free Cash Flow
**FCFF** — calculated via 3 cross-validating methods, all must agree:
- From Net Income: NI + Non-Cash Exp +/- ΔWorking Capital + Interest×(1-Tax) − CapEx
- From NOPAT: NOPAT + Non-Cash Exp +/- ΔWorking Capital − CapEx
- From CFO: CFO + Interest×(1-Tax) − CapEx

**FCFE** — calculated via 3 cross-validating methods, all must agree:
- Direct: NI + Non-Cash Exp +/- ΔWorking Capital − CapEx + Net Borrowing
- From FCFF: FCFF − Interest×(1-Tax) + Net Borrowing
- From OCF: OCF − CapEx + Net Borrowing

### 3.3 Cost of Capital
- Cost of Debt (post-tax): from interest expense / book value of debt, tax-adjusted
- Beta: company-specific
- Cost of Equity (Ke): via CAPM = Risk-free rate + Beta × Equity Risk Premium
- WACC: weighted by book value of debt & equity (Wd, We computed from
  mean/median of historical weights)

### 3.4 Valuation (single-stage DCF, Gordon Growth terminal value)
- **Method A — Intrinsic Equity Value**: discount forecasted FCFE at Ke,
  add PV of Terminal Value (using Terminal Growth Rate = proxy for
  long-run nominal GDP growth), divide by shares outstanding → intrinsic
  share price. Compare to current market price → verdict.
- **Method B — Intrinsic Enterprise Value**: discount forecasted FCFF at
  WACC, add PV of Terminal Value → EV.

### 3.5 Sensitivity Analysis
2D grid: intrinsic share price as a function of (Cost of Equity × Terminal
Growth Rate), matching the reference model's sensitivity table structure.

## 4. Out of Scope (v1)
- Multi-stage DCF (only single-stage Gordon Growth for now)
- Banks/financial institutions (different valuation model entirely)
- Real-time market data beyond what's needed for current price comparison

## 5. Scenarios (BDD-style)

Scenario: Calculate FCFF and verify cross-method agreement
  Given a company's income statement, balance sheet, and cash flow data
  When the FCFF calculator runs all 3 methods (Net Income, NOPAT, CFO)
  Then all 3 results must match within rounding tolerance (0.01%)
  And if they don't match, the agent must flag a data inconsistency error

Scenario: Produce an undervalued/overvalued verdict
  Given forecasted FCFE, Cost of Equity, Terminal Growth Rate, and shares outstanding
  When the DCF valuation completes
  Then the agent returns an intrinsic share price
  And compares it to current market price
  And labels the company Undervalued / Fairly Valued / Overvalued

Scenario: Reject LLM-hallucinated math
  Given any numeric financial calculation
  When the agent needs a computed value
  Then it must call a deterministic Python tool/skill, never compute it via free text reasoning
  And the agent's final report must cite which tool produced each number

Scenario: Generic company support
  Given financial data for any company (not just Cipla)
  When the same pipeline runs
  Then it must produce a structurally identical report
  Without any company-specific hardcoded logic

## 6. Success Criteria for v1
- [ ] All Phase 1 calculators reproduce the Cipla reference numbers within 0.1% tolerance
- [ ] Agent pipeline runs end-to-end for Cipla via natural language request
- [ ] Agent pipeline runs end-to-end for at least one OTHER company (proves genericness)
- [ ] Final report includes verdict + sensitivity table + which tool computed each figure
