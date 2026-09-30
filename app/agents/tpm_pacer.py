"""Shared tokens-per-minute (TPM) pacer for the Groq-backed agents.

Groq's free tier enforces a rolling 60-second tokens-per-minute limit (e.g. 8000).
Because our agents use Tool Calling, they often make TWO LLM calls back-to-back 
inside the same agent (one to select the tool, one to return the result). 
These combined calls easily exceed 8000 tokens and crash the pipeline.

This pacer intercepts all LiteLLM requests, estimates the tokens, and if the 
current rolling window is too full, it sleeps BEFORE sending the request.
"""
import asyncio
import time
import litellm

_TPM_LIMIT = 7500  # Safe margin below 8000
_TPM_WINDOW = 65.0 # Seconds
_token_history = [] # List of (timestamp, estimated_tokens)

def _estimate_tokens(kwargs):
    prompt_chars = 0
    for msg in kwargs.get("messages", []):
        content = msg.get("content", "")
        if isinstance(content, str):
            prompt_chars += len(content)
        else:
            prompt_chars += len(str(content))
    # Roughly 4 chars per token, plus LiteLLM/system prompt overhead
    prompt_tokens = (prompt_chars // 4) + 150
    # Add the requested completion tokens
    max_tokens = kwargs.get("max_tokens", 2000)
    return prompt_tokens + max_tokens

async def _smart_pacer_wait(requested_tokens):
    global _token_history
    while True:
        now = time.monotonic()
        # Evict old entries outside the 65s window
        _token_history = [(t, v) for (t, v) in _token_history if now - t < _TPM_WINDOW]
        current_used = sum(v for t, v in _token_history)
        
        if current_used + requested_tokens > _TPM_LIMIT:
            if not _token_history:
                # Single request is massive (e.g. 8000+). Pass it through and pray, 
                # otherwise we would infinite loop.
                _token_history.append((time.monotonic(), requested_tokens))
                return
            # Sleep until the oldest request in the window expires
            wait_time = _TPM_WINDOW - (now - _token_history[0][0]) + 0.5
            print(f"[pacer] {current_used} used + {requested_tokens} req > {_TPM_LIMIT}. Sleeping {wait_time:.1f}s...", flush=True)
            await asyncio.sleep(wait_time)
        else:
            # We have room in the bucket!
            _token_history.append((time.monotonic(), requested_tokens))
            return

_original_acompletion = litellm.acompletion
_original_completion = litellm.completion

async def _patched_acompletion(*args, **kwargs):
    # Strip OSS model reasoning blocks that crash Groq API
    if "messages" in kwargs:
        for msg in kwargs["messages"]:
            if isinstance(msg, dict) and "reasoning_content" in msg:
                del msg["reasoning_content"]

    # When tool_choice is explicitly "none", strip tools and tool_choice so Groq's
    # API won't fail with "Tool choice is none, but model called a tool" if a smaller
    # model inadvertently attempts to format a tool call in its completion text.
    tool_choice = kwargs.get("tool_choice")
    if tool_choice == "none" or (isinstance(tool_choice, dict) and tool_choice.get("type") == "none"):
        kwargs.pop("tools", None)
        kwargs.pop("tool_choice", None)

    # For reasoning models (e.g. gpt-oss-20b), minimize invisible thinking tokens
    # so completions don't waste 1,500+ tokens and truncate halfway through JSON.
    kwargs.setdefault("reasoning_effort", "low")
                
    # Pace the request dynamically based on token size!
    tokens = _estimate_tokens(kwargs)
    await _smart_pacer_wait(tokens)
    
    return await _original_acompletion(*args, **kwargs)

def _patched_completion(*args, **kwargs):
    if "messages" in kwargs:
        for msg in kwargs["messages"]:
            if isinstance(msg, dict) and "reasoning_content" in msg:
                del msg["reasoning_content"]
    kwargs.setdefault("reasoning_effort", "low")
    return _original_completion(*args, **kwargs)

litellm.acompletion = _patched_acompletion
litellm.completion = _patched_completion

# The ADK callbacks are now no-ops since the pacing is handled seamlessly 
# at the network level by the patched acompletion above!
def mark_llm_activity(callback_context=None, llm_response=None):
    return None

async def cooldown_before_agent(callback_context=None):
    return None
