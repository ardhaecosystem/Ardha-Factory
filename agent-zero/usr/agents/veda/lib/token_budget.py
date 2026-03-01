"""
token_budget.py
Ardha Factory — Phase 4A: Runtime Context Budget Guard
-------------------------------------------------------
Utility library for token estimation and budget calculation.

Placed at: /a0/usr/agents/veda/lib/token_budget.py

Responsibilities:
- Estimate token counts per LoopData component (system, extras, history, user_msg)
- Calculate remaining budget against model context window
- Provide a single is_over_budget() check for the budget guard extension

Design decisions:
- Tries tiktoken first (exact count for known OpenRouter models)
- Falls back to approximate_tokens() heuristic for unknown model aliases
- Adds a 10% safety margin on top of configured threshold to absorb estimation error
- Never raises — returns safe fallback values on any failure

No LLM calls. No file I/O. No side effects.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Avoid circular import at runtime — LoopData is only used for type hints
    from agent import LoopData

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default response reservation — tokens the model needs to write its answer
DEFAULT_RESPONSE_BUFFER = 4096

# Compression trigger: fraction of available budget that triggers summarisation
# 0.85 = trigger when 85% of the non-response-buffer tokens are consumed
DEFAULT_THRESHOLD = 0.85

# How many of the most-recent loop iterations to always keep verbatim
# (never hand these to the summariser)
MIN_VERBATIM_ITERATIONS = 3

# Character-to-token ratio used as fast heuristic when tiktoken is unavailable
_CHARS_PER_TOKEN = 4


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_tiktoken_encoder(model_name: str):
    """
    Return a tiktoken encoder for the given model name, or None if unavailable.

    OpenRouter model names look like "moonshotai/kimi-k2.5" or "x-ai/grok-4.1-fast".
    tiktoken only knows OpenAI model names, so we strip the provider prefix and
    try a direct lookup, then fall back to cl100k_base (GPT-4 family).
    """
    try:
        import tiktoken

        # Try exact match first (works for openai/* models on OpenRouter)
        bare = model_name.split("/")[-1] if "/" in model_name else model_name
        try:
            return tiktoken.encoding_for_model(bare)
        except KeyError:
            pass

        # Fall back to cl100k_base — accurate for most modern models
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def _count_tokens_str(text: str, encoder=None) -> int:
    """
    Count tokens in a string.
    Uses tiktoken encoder when available, falls back to character heuristic.
    """
    if not text:
        return 0
    if encoder is not None:
        try:
            return len(encoder.encode(text))
        except Exception:
            pass
    # Heuristic fallback: divide character count by 4
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _extract_text(obj) -> str:
    """
    Best-effort text extraction from various Agent-Zero message/object types.
    Handles: str, list, objects with .output_text() or .content or .text attributes.
    """
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        parts = []
        for item in obj:
            parts.append(_extract_text(item))
        return "\n".join(p for p in parts if p)
    # Agent-Zero OutputMessage / Message objects
    for attr in ("output_text", "text", "content"):
        val = getattr(obj, attr, None)
        if val is not None:
            if callable(val):
                try:
                    return str(val())
                except Exception:
                    continue
            return str(val)
    # Last resort: str() representation
    return str(obj)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_component_tokens(loop_data, model_name: str = "") -> dict[str, int]:
    """
    Estimate token counts for each component of the current LoopData context.

    Returns a dict with keys:
        system      — assembled system prompt text
        extras      — extras_persistent + extras_temporary combined
        history     — conversation history (all messages)
        user_msg    — current user/superior message
        total       — sum of all components

    Never raises. Returns zeros on any failure.
    """
    result = {
        "system": 0,
        "extras": 0,
        "history": 0,
        "user_msg": 0,
        "total": 0,
    }

    try:
        encoder = _get_tiktoken_encoder(model_name) if model_name else None

        # --- System prompt ---
        if hasattr(loop_data, "system") and loop_data.system:
            sys_text = "\n\n".join(
                _extract_text(s) for s in loop_data.system
            )
            result["system"] = _count_tokens_str(sys_text, encoder)

        # --- Extras (persistent + temporary) ---
        extras_text_parts = []
        for attr in ("extras_persistent", "extras_temporary"):
            extras = getattr(loop_data, attr, None)
            if extras and isinstance(extras, dict):
                for v in extras.values():
                    extras_text_parts.append(_extract_text(v))
        result["extras"] = _count_tokens_str(
            "\n".join(extras_text_parts), encoder
        )

        # --- History ---
        history_text_parts = []
        history_output = getattr(loop_data, "history_output", None)
        if history_output and isinstance(history_output, list):
            for msg in history_output:
                history_text_parts.append(_extract_text(msg))
        result["history"] = _count_tokens_str(
            "\n".join(history_text_parts), encoder
        )

        # --- Current user message ---
        user_msg = getattr(loop_data, "user_message", None)
        result["user_msg"] = _count_tokens_str(
            _extract_text(user_msg), encoder
        )

        result["total"] = (
            result["system"]
            + result["extras"]
            + result["history"]
            + result["user_msg"]
        )

    except Exception as e:
        print(f"[Veda:TokenBudget] WARN: estimation failed: {e}")

    return result


def get_budget_status(
    loop_data,
    ctx_length: int,
    model_name: str = "",
    threshold: float = DEFAULT_THRESHOLD,
    response_buffer: int = DEFAULT_RESPONSE_BUFFER,
) -> dict:
    """
    Return a full budget status report for the current context.

    Returns a dict with:
        tokens          — component breakdown (from estimate_component_tokens)
        ctx_length      — total model context window
        available       — ctx_length minus response_buffer
        threshold_tokens — the token count that triggers compression
        over_budget     — True if compression should be triggered
        utilisation_pct — percentage of available budget consumed (0–100)
    """
    tokens = estimate_component_tokens(loop_data, model_name)
    available = max(ctx_length - response_buffer, 1)
    threshold_tokens = int(available * threshold)
    over = tokens["total"] > threshold_tokens
    utilisation = round((tokens["total"] / available) * 100, 1)

    return {
        "tokens": tokens,
        "ctx_length": ctx_length,
        "available": available,
        "threshold_tokens": threshold_tokens,
        "over_budget": over,
        "utilisation_pct": utilisation,
    }


def is_over_budget(
    loop_data,
    ctx_length: int,
    model_name: str = "",
    threshold: float = DEFAULT_THRESHOLD,
    response_buffer: int = DEFAULT_RESPONSE_BUFFER,
) -> bool:
    """
    Fast boolean check: should compression be triggered right now?
    Convenience wrapper around get_budget_status().
    """
    status = get_budget_status(
        loop_data, ctx_length, model_name, threshold, response_buffer
    )
    return status["over_budget"]
