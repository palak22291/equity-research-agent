"""Offline data agent — serves cached fixture data instead of calling the MCP server.

Used in --offline mode for demo safety: no yfinance, no network, and no LLM call for
the data step. It writes temp:financial_data to session state exactly like the online
data_agent's output_key would, so the rest of the pipeline is unchanged.
"""
import json
from pathlib import Path
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "cipla_fy2026.json"


class OfflineDataAgent(BaseAgent):
    """Reads the cached fixture and writes it to temp:financial_data (no LLM, no network).

    Fields are declared as pydantic model fields (BaseAgent forbids extra attributes).
    """

    fixture_path: str
    beta_override: float = 0.0

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        path = Path(self.fixture_path)
        if not path.exists():
            payload = json.dumps({
                "error": f"Offline fixture not found at {path}. "
                         "Run `python3 scripts/save_fixture.py` first."
            })
        else:
            data = json.loads(path.read_text())
            # Honour a CLI beta override in offline mode too (mirrors the MCP tool).
            if self.beta_override and self.beta_override > 0:
                data["beta"] = self.beta_override
                data["beta_source"] = "user_provided"
                data["beta_override_note"] = (
                    f"offline fixture beta replaced by analyst-provided beta ({self.beta_override})"
                )
            payload = json.dumps(data)

        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=types.Content(role="model", parts=[types.Part(text=payload)]),
            actions=EventActions(state_delta={"temp:financial_data": payload}),
        )


def create_offline_data_agent(beta_override: float = 0.0) -> OfflineDataAgent:
    return OfflineDataAgent(
        name="data_agent",
        fixture_path=str(_FIXTURE_PATH),
        beta_override=beta_override,
    )
