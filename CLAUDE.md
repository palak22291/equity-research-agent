# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AI Equity Research Analyst — a multi-agent system built with Google ADK that produces institutional-grade equity research reports. Agents collaborate via skills and MCP servers to fetch data, run financial models, and synthesize analysis.

## Tech Stack

- **Python** — primary language
- **Google ADK** — multi-agent orchestration framework
- **MCP servers** — tool/data access layer (`app/mcp/`)
- **Agent Skills** — reusable capabilities shared across agents (`app/skills/`)

## Commands

```bash
# Run all tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_calculators.py -v

# Run a specific test
python -m pytest tests/test_calculators.py::test_wacc -v
```

## Directory Structure

```
app/
  calculators/   # Deterministic Python financial math functions
  agents/        # Google ADK agent definitions
  skills/        # Agent skills (reusable across agents)
  mcp/           # MCP server definitions
specs/           # Feature and system specifications
tests/           # Unit tests (mirrors app/ structure)
```

## Critical Financial Math Rule

**NEVER compute financial math in LLM reasoning text.** All calculations — WACC, DCF, FCFE, FCFF, valuation ratios, or any derived financial metric — must be implemented as deterministic Python functions in `app/calculators/` and called explicitly. LLMs must only interpret and narrate the outputs of these functions, never perform the arithmetic themselves.

This exists because LLM floating-point reasoning is non-deterministic and unauditable. Every number in a research report must be traceable to a specific Python function call with known inputs.

## Calculator Requirements

- Every calculator in `app/calculators/` must have corresponding unit tests in `tests/` validated against **Cipla FY2025 verified reference numbers** before the calculator is wired into any agent pipeline.
- FCFF and FCFE must each be computed via **3 independent methods** that cross-validate against each other. A discrepancy beyond tolerance must raise an error, not silently pick one result.
- Calculators must be **generic** — they accept financial inputs as parameters and work for any company. Never hardcode company names, ticker symbols, or company-specific constants inside calculator logic.

## Before Implementing Any Feature

Always read `specs/equity_research_agent.md` before implementing a new feature or agent. Specs define the expected inputs, outputs, and validation criteria that tests must enforce.
