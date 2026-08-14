"""Orchestrator — coordinates the 4-agent equity research pipeline in sequence."""
import warnings

# SequentialAgent is deprecated in ADK 2.x (use Workflow in production),
# but still fully functional and the clearest way to express a fixed sequence.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from google.adk.agents import SequentialAgent

from app.agents.analysis_agent import create_analysis_agent
from app.agents.data_agent import create_data_agent
from app.agents.offline_data_agent import create_offline_data_agent
from app.agents.report_agent import create_report_agent
from app.agents.valuation_agent import create_valuation_agent


def build_orchestrator(offline: bool = False, beta_override: float = 0.0) -> SequentialAgent:
    """Build the 4-agent sequential pipeline.

    When offline=True the data step serves cached fixture data instead of
    calling yfinance. Both modes use a custom BaseAgent (no LLM) for the
    data step; only the analysis/valuation/report agents use Groq.

    Fresh sub-agent instances are created on every call via the per-agent factories, so
    two orchestrators never share a sub-agent (ADK forbids a sub-agent having two
    parents).
    """
    data_step = create_offline_data_agent(beta_override) if offline else create_data_agent(beta_override)
    return SequentialAgent(
        name="equity_research_orchestrator",
        sub_agents=[
            data_step,
            create_analysis_agent(),
            create_valuation_agent(),
            create_report_agent(),
        ],
    )


# Backward-compatible module-level singleton (online pipeline).
equity_research_orchestrator = build_orchestrator()
