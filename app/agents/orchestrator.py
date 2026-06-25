"""Orchestrator — coordinates the 4-agent equity research pipeline in sequence."""
import warnings

# SequentialAgent is deprecated in ADK 2.x (use Workflow in production),
# but still fully functional and the clearest way to express a fixed sequence.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from google.adk.agents import SequentialAgent

from app.agents.data_agent import data_agent
from app.agents.analysis_agent import analysis_agent
from app.agents.valuation_agent import valuation_agent
from app.agents.report_agent import report_agent

equity_research_orchestrator = SequentialAgent(
    name="equity_research_orchestrator",
    sub_agents=[
        data_agent,
        analysis_agent,
        valuation_agent,
        report_agent,
    ],
)
