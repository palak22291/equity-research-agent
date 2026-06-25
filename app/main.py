"""Entry point for the equity research agent pipeline.

Usage:
    python3 -m app.main CIPLA pharmaceuticals
    python3 -m app.main INFY it
    python3 -m app.main                          # prompts for ticker and sector

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

_SEP = "-" * 60


def _preview(text: str, limit: int = 300) -> str:
    text = text.strip().replace("\n", " ")
    return text[:limit] + "..." if len(text) > limit else text


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

    print(f"\n{_SEP}")
    print(f"[pipeline] Starting: {ticker} / {sector}")
    print(f"[pipeline] Session: {session.id}")
    print(_SEP)

    # Track accumulated state so we can inspect it after each agent step.
    # (session returned by create_session is a snapshot; state_delta in events
    # is the authoritative source of what each agent wrote to state.)
    accumulated_state: dict = {}
    current_author: str | None = None
    final_report = ""

    try:
        async for event in runner.run_async(
            user_id="analyst",
            session_id=session.id,
            new_message=message,
        ):
            author = getattr(event, "author", None) or "unknown"

            # ── Agent transition ──────────────────────────────────────────
            if author != current_author:
                if current_author is not None:
                    print(f"\n[{current_author}] finished")
                    print(f"[state] keys so far: {sorted(accumulated_state.keys()) or '(none)'}")
                current_author = author
                print(f"\n{_SEP}")
                print(f"[{author}] started")

            # ── Tool calls ────────────────────────────────────────────────
            if event.get_function_calls():
                for fc in event.get_function_calls():
                    arg_keys = list(fc.args.keys()) if fc.args else []
                    print(f"[{author}]   → tool: {fc.name}({arg_keys})")

            # ── Tool responses ────────────────────────────────────────────
            if event.get_function_responses():
                for fr in event.get_function_responses():
                    resp_text = str(fr.response)
                    print(f"[{author}]   ← tool result ({len(resp_text)} chars): {_preview(resp_text, 200)}")

            # ── State writes ──────────────────────────────────────────────
            if event.actions and event.actions.state_delta:
                for key, val in event.actions.state_delta.items():
                    val_str = str(val)
                    accumulated_state[key] = val
                    print(f"[{author}]   ✓ state['{key}'] written ({len(val_str)} chars)")

            # ── Final response ────────────────────────────────────────────
            if event.is_final_response():
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            print(f"[{author}]   final text ({len(part.text)} chars): {_preview(part.text)}")
                            if author == "report_agent":
                                final_report = part.text

    except KeyError as exc:
        print(f"\n[ERROR] KeyError — context variable missing in state: {exc}")
        print(f"[ERROR] Accumulated state keys at failure: {sorted(accumulated_state.keys()) or '(none)'}")
        print("[ERROR] This means a previous agent did not write its output_key to state.")
        print("[ERROR] Check that data_agent actually produced a text response (not just a tool call).")
        raise
    except Exception as exc:
        print(f"\n[ERROR] Pipeline failed: {type(exc).__name__}: {exc}")
        raise

    # Final state summary
    print(f"\n{_SEP}")
    print(f"[pipeline] Complete. Final state keys: {sorted(accumulated_state.keys())}")

    # Prefer state-stored final_report over event-captured one
    if "final_report" in accumulated_state:
        final_report = accumulated_state["final_report"]

    # Check for upstream error blobs stored in state
    for key in ("temp:financial_data", "temp:analysis_results", "temp:valuation_results"):
        val = accumulated_state.get(key, "")
        if val and '"error"' in str(val)[:100]:
            print(f"[WARN] {key} contains an error payload: {_preview(str(val), 200)}")

    return final_report


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
        print(f"\n{'=' * 60}")
        print(report)
    else:
        print("\n[pipeline] No final report produced — check debug output above.")


if __name__ == "__main__":
    main()
