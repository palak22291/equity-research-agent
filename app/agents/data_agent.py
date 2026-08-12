"""Data agent — fetches all financial data via the financial-data MCP server.

The data source is the FastMCP server in app/mcp/financial_data_server.py, launched
as a stdio subprocess and connected through ADK's MCPToolset. The agent calls the
server's `fetch_all_financial_data` tool — a genuine MCP tool call, not a direct
Python invocation of the provider.
"""
import os
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StdioConnectionParams,
    StdioServerParameters,
)

from app.agents.tpm_pacer import cooldown_before_agent, mark_llm_activity

# Project root so the MCP server subprocess can import the `app` package when
# launched via `python3 -m app.mcp.financial_data_server` (cwd is added to sys.path).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Connect to the financial-data MCP server over stdio. Only the aggregating
# `fetch_all_financial_data` tool is exposed to this agent (the server also
# offers the three lower-level tools, which this agent does not need).
financial_data_mcp = MCPToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="python3",
            args=["-m", "app.mcp.financial_data_server"],
            cwd=str(_PROJECT_ROOT),
        ),
        timeout=120.0,
    ),
    tool_filter=["fetch_all_financial_data"],
)


def create_data_agent() -> LlmAgent:
    return LlmAgent(
        name="data_agent",
        model=LiteLlm(
            # Use the 8B model: this agent's job is trivial (call one tool, echo
            # its JSON). The 70B model consumed ~9.4k tokens on just the first of
            # its two LLM rounds, leaving no headroom for the second round within
            # Groq's 12k tokens-per-minute free-tier limit. The 8B model produces
            # identical results here with ~3× fewer tokens.
            model="groq/llama-3.1-8b-instant",
            api_key=os.environ.get("GROQ_API_KEY"),
            # Cap completion tokens so Groq reserves only what the output needs
            # (this agent echoes a ~430-token JSON), keeping each request well
            # under the 12k tokens-per-minute limit. Without a cap, Groq reserves
            # a large default and inflates the per-request token count.
            max_tokens=1200,
        ),
        instruction="""You have ONE tool available called exactly: fetch_all_financial_data
Call it EXACTLY ONCE with (ticker, sector) from the user message.
If the user message contains "beta_override=<value>", extract that number and pass it \
as the beta_override argument.
After the tool returns, immediately output the raw JSON string it returned.
Do not call the tool again. Do not prefix or namespace the tool name.
Do not add any commentary, analysis, explanation, or markdown.
Your entire response must be the raw JSON string from the tool and nothing else.""",
        tools=[financial_data_mcp],
        output_key="temp:financial_data",
        # Timestamp each LLM call so downstream agents' cooldowns fire correctly.
        before_agent_callback=cooldown_before_agent,
        after_model_callback=mark_llm_activity,
    )


data_agent = create_data_agent()
