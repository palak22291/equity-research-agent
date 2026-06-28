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
            model="groq/llama-3.3-70b-versatile",
            api_key=os.environ.get("GROQ_API_KEY"),
        ),
        instruction="""Call fetch_all_financial_data(ticker, sector) EXACTLY ONCE.
Use the ticker and sector from the user message.
If the user message contains "beta_override=<value>", extract that number and pass it \
as the beta_override argument to fetch_all_financial_data.
After the tool returns, immediately output the raw JSON string it returned.
Do not call the tool again.
Do not add any commentary, analysis, explanation, or markdown.
Your entire response must be the raw JSON string from the tool and nothing else.""",
        tools=[financial_data_mcp],
        output_key="temp:financial_data",
    )


data_agent = create_data_agent()
