"""Shared tokens-per-minute (TPM) pacer for the Groq-backed agents.

Groq's free tier enforces a rolling 60-second tokens-per-minute limit (varies by
model). Each agent's own burst fits under that limit, but two agents' bursts
back-to-back do not — so a full window must separate the *last* LLM call of one
agent from the *first* LLM call of the next.

The cooldown must happen BEFORE an agent's first LLM call. ADK only emits an
agent's first event *after* that call returns, so a reactive sleep in the runner
loop fires too late (the request — and the 429 — already happened). The correct
hook is `before_agent_callback`, which runs before the agent's LLM flow starts.

Usage (per LLM agent):
    LlmAgent(
        ...,
        before_agent_callback=cooldown_before_agent,
        after_model_callback=mark_llm_activity,
    )

The pacer is time-based: it records when the most recent LLM call completed and
only sleeps for the remainder of the window. Agents that make no LLM call (e.g.
the offline data step) never mark activity, so the next agent's cooldown is a
no-op until something has actually consumed tokens.
"""
import asyncio
import time

# Rolling TPM window length, plus a small safety margin so the previous agent's
# tokens are comfortably aged out before the next request is sent.
_WINDOW_SECONDS = 62.0

# Monotonic timestamp of the most recently completed LLM call across all agents.
# 0.0 means no LLM call has happened yet this process.
_last_llm_activity = 0.0


def mark_llm_activity(callback_context=None, llm_response=None):
    """after_model_callback: record that an LLM call just completed.

    Accepts ADK's (callback_context, llm_response) arguments but ignores them.
    Returns None so ADK uses the model's real response unchanged.
    """
    global _last_llm_activity
    _last_llm_activity = time.monotonic()
    return None


async def cooldown_before_agent(callback_context=None):
    """before_agent_callback: wait out the remainder of the TPM window.

    Sleeps only as long as needed so a full window separates the previous agent's
    last LLM call from this agent's first one. No-op when nothing has run yet.
    Returns None so the agent proceeds normally.
    """
    if _last_llm_activity == 0.0:
        return None  # nothing has consumed tokens yet — no need to wait

    wait = _WINDOW_SECONDS - (time.monotonic() - _last_llm_activity)
    if wait > 0:
        name = getattr(callback_context, "agent_name", "next agent")
        print(f"[pipeline] TPM cooldown: waiting {wait:.0f}s before {name}...", flush=True)
        await asyncio.sleep(wait)
    return None
