"""Entry point for the equity research agent pipeline.

Usage:
    python -m app.main CIPLA pharmaceuticals
    python -m app.main INFY it
    python -m app.main                          # prompts for ticker and sector

Requires:
    GEMINI_API_KEY environment variable (or GOOGLE_API_KEY)
"""
import asyncio
import os
import sys

# Use Gemini API key (not Vertex AI)
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")

from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agents.orchestrator import equity_research_orchestrator


async def run_pipeline(ticker: str, sector: str) -> str:
    """Run the full equity research pipeline and return the final markdown report."""
    runner = InMemoryRunner(
        agent=equity_research_orchestrator,
        app_name="equity_research_agent",
    )

    session = await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id="analyst",
    )

    message = types.Content(
        role="user",
        parts=[types.Part(text=f"Analyze {ticker} in {sector} sector")],
    )

    print(f"\nRunning equity research pipeline for {ticker} ({sector})...\n")
    print("=" * 60)

    final_text = ""
    async for event in runner.run_async(
        user_id="analyst",
        session_id=session.id,
        new_message=message,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    final_text = part.text

    return final_text


def main():
    if len(sys.argv) >= 3:
        ticker = sys.argv[1].upper()
        sector = sys.argv[2].lower()
    elif len(sys.argv) == 2:
        ticker = sys.argv[1].upper()
        sector = input(f"Enter sector for {ticker} (e.g. pharmaceuticals, it, banking): ").strip().lower()
    else:
        ticker = input("Enter stock ticker (e.g. CIPLA, INFY): ").strip().upper()
        sector = input("Enter sector (e.g. pharmaceuticals, it, banking): ").strip().lower()

    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
        print("Error: Set GEMINI_API_KEY (or GOOGLE_API_KEY) environment variable.")
        sys.exit(1)

    report = asyncio.run(run_pipeline(ticker, sector))

    if report:
        print(report)
    else:
        print("Pipeline completed. Check individual agent outputs above.")


if __name__ == "__main__":
    main()
