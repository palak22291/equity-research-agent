"""Data agent — fetches all financial data by calling the provider directly.

The previous LLM-based approach (call MCP tool via LlmAgent, echo JSON) was
fragile: the 70B model exceeded Groq's 12k TPM limit, and the 8B model
couldn't reliably output raw JSON (it wrapped it in quotes, triple-braces,
etc.). Since this agent's job is purely mechanical (call a function, return
the result), it now uses a custom BaseAgent — no LLM, no MCP subprocess,
no parsing issues.

The underlying data source is the same YFinanceProvider used by the MCP
server. This agent calls `fetch_all_financial_data()` directly in-process.
"""
import json
import os
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

# Re-use the same aggregation logic that the MCP server's
# `fetch_all_financial_data` tool calls under the hood.
from app.mcp.financial_data_server import fetch_all_financial_data as _fetch


class OnlineDataAgent(BaseAgent):
    """Fetches live financial data via yfinance (no LLM, no MCP subprocess).

    Calls the same `fetch_all_financial_data` function that the MCP server
    exposes, but directly in-process. Writes the JSON result to
    temp:financial_data in session state, matching the output_key contract
    expected by downstream agents.
    """

    beta_override: float = 0.0

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        # Extract ticker and sector from the user message.
        ticker, sector = self._parse_user_message(ctx)

        try:
            data = _fetch(
                ticker=ticker,
                sector=sector,
                beta_override=self.beta_override,
            )
        except Exception as exc:
            data = {"error": f"fetch_all_financial_data failed: {exc}"}

        payload = json.dumps(data)

        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=types.Content(role="model", parts=[types.Part(text=payload)]),
            actions=EventActions(state_delta={"temp:financial_data": payload}),
        )

    @staticmethod
    def _parse_user_message(ctx: InvocationContext) -> tuple[str, str]:
        """Extract ticker and sector from the user prompt.

        Expected format: 'Analyze TICKER in SECTOR sector [with beta_override=X]'
        """
        text = ""
        if ctx.user_content and ctx.user_content.parts:
            text = ctx.user_content.parts[0].text or ""

        # Fallback defaults
        ticker = "CIPLA"
        sector = "pharmaceuticals"

        parts = text.split()
        # "Analyze TICKER in SECTOR sector"
        if len(parts) >= 2:
            ticker = parts[1].upper()
        if len(parts) >= 4:
            sector = parts[3].lower()

        return ticker, sector


def create_data_agent(beta_override: float = 0.0) -> OnlineDataAgent:
    return OnlineDataAgent(
        name="data_agent",
        beta_override=beta_override,
    )


data_agent = create_data_agent()
