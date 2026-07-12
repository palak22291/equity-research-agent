"""FastAPI backend for the equity research agent web dashboard.

Run with:
    python3 -m uvicorn app.api:app --reload --port 8000

Then open http://localhost:8000 in your browser.

Requires:
    pip install fastapi uvicorn
    GROQ_API_KEY environment variable (for live analysis)
"""
from __future__ import annotations
import json
import re
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.main import run_pipeline
from app.security.guardrails import validate_beta, validate_sector, validate_ticker

_FRONTEND = Path(__file__).parent.parent / "frontend" / "index.html"

app = FastAPI(title="Equity Research Agent", version="1.0.0")


class AnalyzeRequest(BaseModel):
    ticker: str
    sector: str
    beta: float | None = None
    offline: bool = False


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/", response_class=HTMLResponse)
async def root():
    if not _FRONTEND.exists():
        raise HTTPException(status_code=404, detail="Frontend not found at frontend/index.html")
    return HTMLResponse(_FRONTEND.read_text())


# LLM agents occasionally wrap their JSON output in a markdown code fence.
_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*\n(.*?)\n?```$", re.DOTALL)


def _parse_stage(raw, stage: str) -> dict:
    """Parse one pipeline stage's JSON output, or fail loudly with a 502.

    A stage that produced nothing, non-JSON, or an {"error": ...} payload means
    the pipeline result is unusable — surfacing that as a gateway error beats the
    old behaviour of returning 200 OK with an all-null dashboard.
    """
    if isinstance(raw, dict):
        parsed = raw
    else:
        text = str(raw).strip() if raw else ""
        if not text:
            raise HTTPException(
                status_code=502,
                detail=f"pipeline stage '{stage}' produced no output",
            )
        fenced = _FENCE_RE.match(text)
        if fenced:
            text = fenced.group(1).strip()
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(
                status_code=502,
                detail=f"pipeline stage '{stage}' returned unparseable output: "
                       f"{text[:200]}",
            )
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=502,
            detail=f"pipeline stage '{stage}' returned {type(parsed).__name__}, expected object",
        )
    if "error" in parsed:
        raise HTTPException(
            status_code=502,
            detail=f"pipeline stage '{stage}' failed: {parsed['error']}",
        )
    return parsed


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    # Validate all inputs at the boundary before touching the pipeline.
    try:
        ticker = validate_ticker(req.ticker)
        sector = validate_sector(req.sector)
        beta   = validate_beta(req.beta)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        report, agent_outputs = await run_pipeline(
            ticker, sector, beta, offline=req.offline
        )
    except ValueError as exc:
        # e.g. offline mode requested for a ticker the fixture doesn't cover.
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        # Surface a clean message — the full traceback goes to server stdout.
        msg = str(exc)
        # Trim litellm's verbose rate-limit blobs to the human-readable part.
        if "GroqException" in msg:
            try:
                blob = json.loads(msg[msg.index("{"):])
                msg = blob["error"]["message"]
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=msg)

    # Each agent writes its final text (JSON string) into agent_outputs.
    # data_agent      → raw financial data JSON
    # analysis_agent  → {"ratio_analysis": {...}, "cashflow_analysis": {...}}
    # valuation_agent → {"cost_of_capital": {...}, "dcf_valuation": {...}}
    # report_agent    → markdown string (already in `report`)
    financial   = _parse_stage(agent_outputs.get("data_agent"), "data_agent")
    analysis    = _parse_stage(agent_outputs.get("analysis_agent"), "analysis_agent")
    valuation   = _parse_stage(agent_outputs.get("valuation_agent"), "valuation_agent")

    ratio_analysis    = analysis.get("ratio_analysis", {})
    cashflow_analysis = analysis.get("cashflow_analysis", {})
    coc         = valuation.get("cost_of_capital", {})
    dcf         = valuation.get("dcf_valuation", {})
    equity_val  = dcf.get("equity_valuation", {})
    fcff        = cashflow_analysis.get("fcff", {})
    fcfe        = cashflow_analysis.get("fcfe", {})
    capm        = coc.get("capm_breakdown", {})
    weights     = coc.get("weights", {})

    # The calculators nest their outputs (liquidity/solvency/profitability/...,
    # fcff/fcfe, capm_breakdown/weights) — that schema is validated by tests and
    # consumed by report_agent, so it stays as-is. The frontend dashboard just
    # wants a flat subset of it, so we flatten here at the HTTP boundary.
    liquidity     = ratio_analysis.get("liquidity", {})
    solvency      = ratio_analysis.get("solvency", {})
    profitability = ratio_analysis.get("profitability", {})
    efficiency    = ratio_analysis.get("efficiency", {})
    ratios = {
        "current_ratio":       liquidity.get("current_ratio"),
        "quick_ratio":         liquidity.get("quick_ratio"),
        "interest_coverage":   solvency.get("interest_coverage"),
        "debt_to_equity":      solvency.get("debt_to_equity"),
        "gross_profit_margin": profitability.get("gross_profit_margin"),
        "net_profit_margin":   profitability.get("net_profit_margin"),
        "return_on_equity":    profitability.get("return_on_equity"),
        "asset_turnover":      efficiency.get("asset_turnover"),
    }
    cashflows = {
        "fcff_m1":        fcff.get("method_1_net_income"),
        "fcff_m2":        fcff.get("method_2_nopat"),
        "fcff_m3":        fcff.get("method_3_cfo"),
        "validated_fcff": fcff.get("validated_fcff"),
        "validated_fcfe": fcfe.get("validated_fcfe"),
    }
    cost_of_capital = {
        **coc,
        "risk_free_rate": capm.get("risk_free_rate"),
        "beta":           capm.get("beta"),
        "market_return":  capm.get("market_return"),
        "wd":             weights.get("wd"),
        "we":             weights.get("we"),
    }

    return {
        # Company metadata (for the dashboard header)
        "ticker":          financial.get("ticker", ticker),
        "company_name":    financial.get("company_name", ticker),
        "fiscal_year_end": financial.get("fiscal_year_end"),
        "sector":          financial.get("sector", sector),
        # Top-level summary fields (duplicated for easy JS access)
        "intrinsic_share_price":  equity_val.get("intrinsic_share_price"),
        "market_price":           equity_val.get("current_market_price"),
        "verdict":                equity_val.get("verdict"),
        "wacc":                   coc.get("wacc"),
        "ke":                     coc.get("ke"),
        "beta":                   beta,
        "terminal_growth_rate":   dcf.get("inputs", {}).get("terminal_growth_rate"),
        "sensitivity":            dcf.get("sensitivity_analysis", {}),
        # Structured blocks for the dashboard cards
        "ratios":          ratios,
        "cashflows":       cashflows,
        "cost_of_capital": cost_of_capital,
        "dcf":             dcf,
        # Full markdown report for the expandable section
        "report":          report,
    }
