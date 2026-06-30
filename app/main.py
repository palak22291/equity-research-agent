from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root explicitly
load_dotenv(Path(__file__).parent.parent / ".env")

"""Entry point for the equity research agent pipeline.

Usage:
    python3 -m app.main CIPLA pharmaceuticals
    python3 -m app.main CIPLA pharmaceuticals 0.4468
    python3 -m app.main INFY it
    python3 -m app.main                          # prompts for ticker and sector
    python3 -m app.main --offline                # demo mode: cached Cipla fixture, no yfinance
    python3 -m app.main CIPLA pharmaceuticals 0.4468 --offline

Requires:
    GROQ_API_KEY environment variable
    For --offline: tests/fixtures/cipla_fy2026.json (run scripts/save_fixture.py once)
"""
import asyncio
import os
import sys

import litellm

# Retry up to 6 times on rate-limit errors, with exponential backoff.
# Groq's TPM window resets every 60s; retries cover within-agent bursts.
litellm.num_retries = 6
litellm.retry_after = 5  # minimum seconds before first retry

# Use Gemini key path (not Vertex AI)
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")

from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agents.orchestrator import build_orchestrator
from app.security.guardrails import validate_beta, validate_sector, validate_ticker

_SEP = "-" * 60


def _preview(text: str, limit: int = 300) -> str:
    text = text.strip().replace("\n", " ")
    return text[:limit] + "..." if len(text) > limit else text


# Deterministic explanatory note for the DCF sensitivity grid. Appended in Python
# (not by the LLM) so it is always present and never consumes tokens. Cells where
# cost of equity approaches terminal growth rate blow up / are undefined (the
# Gordon Growth denominator ke - g → 0), so the grid shows them as null.
_SENSITIVITY_CAVEAT = (
    "> *Note: cells where cost of equity approaches the terminal growth rate are "
    "mathematically undefined and excluded (shown as null).*"
)
_SENSITIVITY_MARKER = "cost of equity approaches the terminal growth rate"


def _inject_sensitivity_caveat(report: str) -> str:
    """Insert the sensitivity-grid caveat at the end of Section 6, before Section 7.
    Idempotent: does nothing if the note is already present, and is a no-op if the
    report has no Section 6 sensitivity table."""
    if not report or _SENSITIVITY_MARKER in report:
        return report
    if "Sensitivity Analysis" not in report:
        return report

    block = "\n" + _SENSITIVITY_CAVEAT + "\n"
    # Prefer placing it just before the next section heading ("### 7" / "## 7").
    for heading in ("\n### 7", "\n## 7", "\n---"):
        idx = report.find(heading)
        if idx != -1:
            return report[:idx] + "\n" + _SENSITIVITY_CAVEAT + "\n" + report[idx:]
    # Fallback: append at the end of the report.
    return report.rstrip() + "\n" + block


async def run_pipeline(
    ticker: str,
    sector: str,
    beta: float | None = None,
    offline: bool = False,
) -> str:
    """Run the full equity research pipeline and return the final markdown report.

    When offline=True the data step is served from the cached Cipla fixture instead of
    yfinance (no network) — for demo safety. The analysis/valuation/report agents still
    use Groq.
    """
    orchestrator = build_orchestrator(offline=offline, beta_override=beta or 0.0)
    runner = InMemoryRunner(
        agent=orchestrator,
        app_name="equity_research_agent",
    )

    session = await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id="analyst",
    )

    prompt = f"Analyze {ticker} in {sector} sector"
    if beta is not None:
        prompt += f" with beta_override={beta}"

    message = types.Content(
        role="user",
        parts=[types.Part(text=prompt)],
    )

    print(f"\n{_SEP}")
    print(f"[pipeline] Starting: {ticker} / {sector}")
    if offline:
        print("[pipeline] OFFLINE MODE — using cached Cipla fixture data")
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
                    # The offline data step makes no LLM calls, so no TPM cooldown is needed.
                    if offline and current_author == "data_agent":
                        print("[pipeline] (offline data step — skipping TPM cooldown)")
                    else:
                        print("[pipeline] Waiting 60s for TPM limit to reset...")
                        await asyncio.sleep(60)
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

    # Deterministically annotate the sensitivity grid (never left to the LLM).
    final_report = _inject_sensitivity_caveat(final_report)

    return final_report


def main():
    # --offline can appear anywhere; strip it out before positional parsing.
    offline = "--offline" in sys.argv
    argv = [a for a in sys.argv if a != "--offline"]

    beta: float | None = None
    if len(argv) >= 3:
        ticker = argv[1].upper()
        sector = argv[2].lower()
        if len(argv) >= 4:
            try:
                beta = float(argv[3])
            except ValueError:
                print(f"Error: beta must be a number, got '{argv[3]}'")
                sys.exit(1)
    elif len(argv) == 2:
        ticker = argv[1].upper()
        sector = input(f"Enter sector for {ticker} (e.g. pharmaceuticals, it, banking): ").strip().lower()
    elif offline:
        # Offline demo with no positional args: default to the cached Cipla fixture.
        ticker, sector = "CIPLA", "pharmaceuticals"
    else:
        ticker = input("Enter stock ticker (e.g. CIPLA, INFY): ").strip().upper()
        sector = input("Enter sector (e.g. pharmaceuticals, it, banking): ").strip().lower()

    if not os.environ.get("GROQ_API_KEY"):
        print("Error: Set GROQ_API_KEY environment variable.")
        sys.exit(1)

    try:
        ticker = validate_ticker(ticker)
        sector = validate_sector(sector)
        beta   = validate_beta(beta)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    if beta is not None:
        print(f"[pipeline] Using user-provided beta: {beta}")

    report = asyncio.run(run_pipeline(ticker, sector, beta, offline=offline))

    if report:
        print(f"\n{'=' * 60}")
        print(report)
    else:
        print("\n[pipeline] No final report produced — check debug output above.")


if __name__ == "__main__":
    main()
