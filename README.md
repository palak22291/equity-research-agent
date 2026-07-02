# AI Equity Research Analyst

An AI-powered multi-agent system that automates full equity research analysis — from live financial data fetching to DCF valuation and investment verdict — in minutes instead of days.

Built as a capstone project for the **Kaggle × Google 5-Day AI Agents Intensive** (Agents for Business Track, June 2026), applying concepts from the course directly to a real-world finance problem.

---

## Motivation

During my Finance minor, I completed a full equity research project on Cipla Ltd. — manually computing ratios, FCFF/FCFE across three cross-validating methods, CAPM/WACC, DCF valuation, sensitivity analysis, and a final undervalued/overvalued verdict. It took days of careful Excel work.

This project automates that exact workflow using a multi-agent AI system. The goal: make institutional-quality equity research accessible in minutes, not days — while keeping every calculation **deterministic, auditable, and verified**.

---

## What It Does

Give the agent a stock ticker and sector. It produces a complete equity research report:

- **Financial ratio analysis** — liquidity, solvency, profitability, efficiency, DuPont
- **Free cash flow analysis** — FCFF and FCFE each computed via 3 independent cross-validating methods
- **Cost of capital** — CAPM-derived cost of equity, post-tax cost of debt, WACC
- **DCF valuation** — 3-year forecast with Gordon Growth terminal value, intrinsic share price
- **Sensitivity analysis** — 2D grid of intrinsic price across cost of equity × terminal growth rate scenarios
- **Investment verdict** — Undervalued / Fairly Valued / Overvalued vs current market price
- **Web Dashboard** — dark theme UI with live analysis, verdict strip, ratio cards, FCF visualization, and sensitivity analysis table

```bash
python3 -m app.main CIPLA pharmaceuticals
# → Full markdown equity research report in ~5 minutes
```

---

## Architecture

```
User Input (ticker + sector)
         ↓
┌─────────────────────────────────────────────────────┐
│              Equity Research Orchestrator            │
│                  (Google ADK Sequential)             │
└─────────────────────────────────────────────────────┘
         ↓              ↓              ↓              ↓
   Data Agent    Analysis Agent  Valuation Agent  Report Agent
        ↓              ↓              ↓              ↓
   MCP Server    Ratio + FCF     WACC + DCF     Markdown
   (yfinance)    Skills          Skills         Report
```

**4 specialized agents** in a sequential pipeline, each with a single responsibility:

| Agent | Role | Tools |
|---|---|---|
| `data_agent` | Fetch live financial data | yfinance MCP server |
| `analysis_agent` | Ratio + cashflow analysis | Agent Skills (deterministic Python) |
| `valuation_agent` | Cost of capital + DCF | Agent Skills (deterministic Python) |
| `report_agent` | Synthesize results into markdown report | LLM narrative only (no calculations) |

---

## Key Design Principle: No LLM Math

> *"All numerical calculations are performed by deterministic Python calculators — not by the LLM."*

Every financial calculation delegates to verified Python scripts. The LLM orchestrates, narrates, and synthesizes — but never computes a ratio, a WACC, or an intrinsic price itself.

This was a deliberate architectural choice: LLMs produce plausible-sounding but unverifiable numbers. Deterministic tools produce auditable, reproducible results.

---

## Verified Against Academic Ground Truth

The calculation engine was built and tested against a **professor-graded (full marks) equity research project** for Cipla Ltd. FY2025.

**127 unit tests** verify calculators reproduce known-correct outputs:

| Calculator | Tests | Verified Against |
|---|---|---|
| `ratios.py` | 21 | Cipla FY2025 Excel |
| `cashflows.py` | 30 | Cipla FY2025 Excel |
| `cost_of_capital.py` | 36 | Cipla FY2025 Excel |
| `dcf.py` | 13 | Cipla FY2025 Excel |
| `security/guardrails.py` | 27 | Input validation + injection tests |

Key verified outputs for Cipla FY2025:
- WACC: **8.40%**
- Cost of Equity (Ke): **8.44%**
- Intrinsic Share Price: **₹4,934.01**
- Verdict: **Undervalued** vs market price of ₹1,441

---

## Course Concepts Demonstrated

This project applies concepts from all 5 days of the Kaggle × Google AI Agents Intensive:

| Concept | Where Demonstrated |
|---|---|
| Multi-agent system (ADK) | 4-agent sequential pipeline in `app/agents/` |
| MCP Server | yfinance data provider in `app/mcp/` — genuinely wired into execution path |
| Agent Skills | 4 skills with SKILL.md + Python scripts in `app/skills/` — invoked as subprocesses |
| Security guardrails | Input validation in `app/security/guardrails.py` — ticker, sector, beta, numeric output |
| Spec-first development (Day 4) | `specs/equity_research_agent.md` — written before any code |
| Context engineering | `CLAUDE.md` with hard constraints on calculation delegation |

---

## Tech Stack

- **Agent Framework:** Google ADK (Agent Development Kit)
- **LLM:** Groq (llama-3.3-70b-versatile) via LiteLLM
- **Data Source:** yfinance (Yahoo Finance) via custom MCP server
- **Finance Calculations:** Pure Python (no external finance libraries — formulas implemented from scratch)
- **Backend:** FastAPI + uvicorn
- **Frontend:** Single-file dark theme dashboard (HTML/CSS/JS)
- **Testing:** pytest (127 unit tests)
- **Skills:** FastMCP + custom SKILL.md agent skills

---

## Project Structure

```
equity-research-agent/
├── specs/
│   └── equity_research_agent.md    # Spec written before any code
├── app/
│   ├── calculators/                # Deterministic financial math
│   │   ├── ratios.py               # 21 ratio methods
│   │   ├── cashflows.py            # FCFF/FCFE (3-method cross-validation)
│   │   ├── cost_of_capital.py      # CAPM, WACC
│   │   └── dcf.py                  # DCF, sensitivity analysis
│   ├── mcp/                        # MCP data server
│   │   └── providers/
│   │       ├── base.py             # Abstract provider (swappable architecture)
│   │       └── yfinance_provider.py
│   ├── skills/                     # Agent Skills
│   │   ├── ratio-analysis/
│   │   ├── cashflow-analysis/
│   │   ├── cost-of-capital/
│   │   └── valuation/
│   ├── agents/                     # ADK Agents
│   │   ├── data_agent.py
│   │   ├── analysis_agent.py
│   │   ├── valuation_agent.py
│   │   ├── report_agent.py
│   │   └── orchestrator.py
│   ├── security/
│   │   └── guardrails.py           # Input validation
│   ├── api.py                      # FastAPI backend
│   └── main.py                     # CLI entry point
├── frontend/
│   └── index.html                  # Dark theme web dashboard
├── tests/                          # 127 unit tests
├── scripts/
│   └── save_fixture.py             # Generate offline demo fixture
├── CLAUDE.md                       # Context engineering for Claude Code
└── .env                            # API keys (not committed)
```

---

## Setup

### Prerequisites
- Python 3.11+
- Groq API key (free tier at [console.groq.com](https://console.groq.com))

### Installation

```bash
git clone https://github.com/palak22291/equity-research-agent
cd equity-research-agent
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:
```
GROQ_API_KEY=your_groq_api_key_here
```

### Run CLI

```bash
# Analyze any NSE-listed company
python3 -m app.main CIPLA pharmaceuticals
python3 -m app.main INFY it
python3 -m app.main RELIANCE oil_gas

# With verified beta override
python3 -m app.main CIPLA pharmaceuticals 0.4468

# Offline demo mode (no internet required for data fetch)
python3 -m app.main --offline

# Run unit tests
python3 -m pytest tests/ -v
```

### Run Web Dashboard

```bash
python3 -m uvicorn app.api:app --port 8000
# Open http://localhost:8000
```

## Live Demo

**[Try it live →](https://equity-research-agent-jqbe.onrender.com)**

> Note: First load may take 30 seconds (free tier cold start). Use "Offline demo" checkbox for instant Cipla analysis without API calls.
> To run with live data for any NSE stock, clone the repo and add your own free [Groq API key](https://console.groq.com/keys) to `.env`.

### Supported Sectors
`pharmaceuticals` · `it` · `banking` · `fmcg` · `automobiles` · `oil_gas` · `telecom` · `metals` · `cement` · `power` · `healthcare`

### Common NSE Tickers
| Company | Ticker |
|---|---|
| Cipla | CIPLA |
| Infosys | INFY |
| Reliance Industries | RELIANCE |
| HDFC Bank | HDFCBANK |
| TCS | TCS |
| Sun Pharma | SUNPHARMA |
| Wipro | WIPRO |

---

## Sample Output

```markdown
## Cipla Limited — Equity Research Report
Ticker: CIPLA.NS | Sector: Pharmaceuticals

### Key Financial Ratios
| Ratio             | Value  |
| Current Ratio     | 3.44   |
| Interest Coverage | 109.31 |
| Net Profit Margin | 14%    |

### DCF Valuation
| Intrinsic Share Price | ₹3,462 |
| Current Market Price  | ₹1,454 |
| Verdict               | UNDERVALUED ✓ |

*All calculations performed by deterministic Python tools — not LLM reasoning.*
```

---

## About

Built by **Palak Gupta** — 2nd year BTech (CS + AI) student at Rishihood University, with a Finance minor.

This project sits at the intersection of my two academic interests: building AI systems and understanding financial valuation. The calculation engine is directly derived from academic coursework; the agent architecture was built during the Kaggle × Google AI Agents Intensive.

*Kaggle × Google 5-Day AI Agents Intensive · June 2026 · Agents for Business Track*
