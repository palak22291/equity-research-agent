"""API-boundary guards: offline ticker restriction and 502 on unusable pipeline output.

No Groq / network: the offline-ticker guard raises before any agent runs, and the
502 tests monkeypatch run_pipeline with canned agent outputs.
"""
import json

import pytest
from fastapi.testclient import TestClient

import app.api as api

client = TestClient(api.app, raise_server_exceptions=False)

# Minimal happy-path agent outputs (schema subset the /analyze flattener reads).
_FINANCIAL = {"ticker": "CIPLA.NS", "company_name": "Cipla Limited",
              "fiscal_year_end": "2026-03-31", "sector": "pharmaceuticals"}
_ANALYSIS  = {"ratio_analysis": {"liquidity": {"current_ratio": 3.44}},
              "cashflow_analysis": {"fcff": {"validated_fcff": 2585.67},
                                    "fcfe": {"validated_fcfe": 2900.62}}}
_VALUATION = {"cost_of_capital": {"wacc": 0.09, "ke": 0.0915},
              "dcf_valuation": {"equity_valuation": {"intrinsic_share_price": 3462.73,
                                                     "current_market_price": 1454.1,
                                                     "verdict": "Undervalued"}}}


def _fake_pipeline(outputs):
    async def fake(ticker, sector, beta=None, offline=False):
        return "# report", outputs
    return fake


# ── Offline ticker guard ─────────────────────────────────────────────────────

def test_offline_rejects_non_cipla_ticker():
    resp = client.post("/analyze", json={"ticker": "INFY", "sector": "it", "offline": True})
    assert resp.status_code == 400
    assert "offline mode only supports the CIPLA fixture" in resp.json()["detail"]


@pytest.mark.parametrize("ticker", ["CIPLA", "cipla", "CIPLA.NS"])
def test_offline_accepts_cipla_forms(ticker, monkeypatch):
    monkeypatch.setattr(api, "run_pipeline", _fake_pipeline({
        "data_agent": json.dumps(_FINANCIAL),
        "analysis_agent": json.dumps(_ANALYSIS),
        "valuation_agent": json.dumps(_VALUATION),
    }))
    resp = client.post("/analyze",
                       json={"ticker": ticker, "sector": "pharmaceuticals", "offline": True})
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "Undervalued"


# ── 502 on unusable pipeline output ──────────────────────────────────────────

def test_unparseable_stage_returns_502(monkeypatch):
    monkeypatch.setattr(api, "run_pipeline", _fake_pipeline({
        "data_agent": "Sure! Here is the data you asked for...",
        "analysis_agent": json.dumps(_ANALYSIS),
        "valuation_agent": json.dumps(_VALUATION),
    }))
    resp = client.post("/analyze", json={"ticker": "CIPLA", "sector": "pharmaceuticals"})
    assert resp.status_code == 502
    assert "unparseable" in resp.json()["detail"]


def test_missing_stage_returns_502(monkeypatch):
    monkeypatch.setattr(api, "run_pipeline", _fake_pipeline({
        "data_agent": json.dumps(_FINANCIAL),
        # analysis_agent output missing entirely
        "valuation_agent": json.dumps(_VALUATION),
    }))
    resp = client.post("/analyze", json={"ticker": "CIPLA", "sector": "pharmaceuticals"})
    assert resp.status_code == 502
    assert "produced no output" in resp.json()["detail"]


def test_error_payload_returns_502(monkeypatch):
    monkeypatch.setattr(api, "run_pipeline", _fake_pipeline({
        "data_agent": json.dumps({"error": "No income statement data for XYZ.NS"}),
        "analysis_agent": json.dumps(_ANALYSIS),
        "valuation_agent": json.dumps(_VALUATION),
    }))
    resp = client.post("/analyze", json={"ticker": "CIPLA", "sector": "pharmaceuticals"})
    assert resp.status_code == 502
    assert "No income statement data" in resp.json()["detail"]


def test_markdown_fenced_json_is_accepted(monkeypatch):
    """LLMs sometimes wrap JSON in ```json fences — that is parseable, not a 502."""
    monkeypatch.setattr(api, "run_pipeline", _fake_pipeline({
        "data_agent": f"```json\n{json.dumps(_FINANCIAL)}\n```",
        "analysis_agent": json.dumps(_ANALYSIS),
        "valuation_agent": json.dumps(_VALUATION),
    }))
    resp = client.post("/analyze", json={"ticker": "CIPLA", "sector": "pharmaceuticals"})
    assert resp.status_code == 200
    assert resp.json()["company_name"] == "Cipla Limited"
