"""
history_compressor.py
Ardha Factory — Phase 4A: Runtime Context Budget Guard
-------------------------------------------------------
Utility library for compressing conversation history when context budget
approaches the model's limit.

Placed at: /a0/usr/agents/veda/lib/history_compressor.py

Responsibilities:
- Identify which history entries are safe to summarise (older than MIN_VERBATIM)
- Call agent.call_utility_model() to produce a dense summary
- Replace old history entries in loop_data.history_output with the summary
- Compress large extras_persistent entries that exceed a token threshold
- Record compression metadata in loop_data.params_persistent for audit use

Design decisions:
- Always keeps the last MIN_VERBATIM_ITERATIONS messages verbatim
- Uses agent's own utility model (Grok 4.1 Fast in Ardha config) — no extra cost
- Summary is injected as a single synthetic message marked [COMPRESSED HISTORY]
- If utility model call fails, original history is left untouched (fail-open)
- Extras entries larger than EXTRAS_COMPRESS_THRESHOLD tokens are individually
  summarised and replaced in extras_persistent
- Never touches: system prompt, extras_temporary, current user message

No file I/O. No governance state access.
"""

from __future__ import annotations

import sys
import os
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LIB_DIR = "/a0/usr/agents/veda/lib"

# Minimum number of recent history_output entries to always keep verbatim
MIN_VERBATIM_ENTRIES = 6  # ~3 iterations × 2 messages (AI response + tool result)

# extras_persistent values larger than this (tokens) are candidates for
# individual summarisation
EXTRAS_COMPRESS_THRESHOLD = 800  # tokens

# Target compression ratio for history summary (summary should be ≤ this
# fraction of the original token count)
TARGET_SUMMARY_RATIO = 0.25

# Label injected into history so the agent knows compression occurred
COMPRESSION_LABEL = "[COMPRESSED HISTORY — earlier context summarised]"

# Label for compressed extras entries
EXTRAS_LABEL = "[COMPRESSED MEMORY RECALL]"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _import_token_budget():
    """Lazy import of token_budget from the lib directory."""
    if LIB_DIR not in sys.path:
        sys.path.insert(0, LIB_DIR)
    from token_budget import _extract_text, _count_tokens_str, _get_tiktoken_encoder
    return _extract_text, _count_tokens_str, _get_tiktoken_encoder


def _build_history_text(history_output: list, extract_fn) -> str:
    """Convert history_output list into a single text block for summarisation."""
    parts = []
    for i, msg in enumerate(history_output):
        text = extract_fn(msg)
        if text.strip():
            parts.append(f"[Message {i + 1}]\n{text.strip()}")
    return "\n\n".join(parts)


def _build_summary_system_prompt() -> str:
    return (
        "You are a precise context summariser for an AI agent system.\n"
        "Your task: compress a conversation history into a dense, structured summary.\n\n"
        "RULES:\n"
        "1. Preserve ALL of the following with exact detail:\n"
        "   - Every tool call made and its outcome (success/failure/output)\n"
        "   - Every file path created, modified, or deleted\n"
        "   - Every decision made by the agent\n"
        "   - Every error encountered and how it was resolved\n"
        "   - Every spec ID, team name, agent name, or registry operation\n"
        "   - Any pending actions or unresolved issues\n"
        "2. Remove: verbose reasoning, repeated content, decorative language\n"
        "3. Format: numbered chronological list of actions and outcomes\n"
        "4. Start directly with the list — no preamble, no headers\n"
        "5. Be maximally dense. Every word must carry information.\n"
    )


def _build_summary_message(history_text: str) -> str:
    return (
        f"Compress the following agent conversation history into a dense summary "
        f"following the rules in your system prompt.\n\n"
        f"HISTORY TO COMPRESS:\n{history_text}"
    )


def _build_extras_system_prompt() -> str:
    return (
        "You are a precise memory summariser for an AI agent system.\n"
        "Compress the following recalled memory text into a shorter version.\n\n"
        "RULES:\n"
        "1. Preserve all factual content: names, IDs, paths, decisions, outcomes\n"
        "2. Remove verbose formatting, repetition, and filler text\n"
        "3. Output plain prose — no headers, no bullet points unless they were in the original\n"
        "4. Be maximally dense. Target 20-25% of the original length.\n"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def compress_history(agent, loop_data, model_name: str = "") -> dict:
    """
    Summarise older history_output entries using the agent's utility model.

    Keeps the last MIN_VERBATIM_ENTRIES entries verbatim.
    Replaces all older entries with a single synthetic summary message.

    Returns a metadata dict describing what was done:
        {
            "triggered": bool,
            "original_entries": int,
            "kept_verbatim": int,
            "compressed_entries": int,
            "summary_produced": bool,
            "error": str | None,
        }
    """
    meta = {
        "triggered": False,
        "original_entries": 0,
        "kept_verbatim": 0,
        "compressed_entries": 0,
        "summary_produced": False,
        "error": None,
    }

    try:
        _extract_text, _count_tokens_str, _get_tiktoken_encoder = _import_token_budget()

        history_output = getattr(loop_data, "history_output", None)
        if not history_output or not isinstance(history_output, list):
            return meta

        total_entries = len(history_output)
        meta["original_entries"] = total_entries

        # Not enough entries to compress — need more than verbatim window
        if total_entries <= MIN_VERBATIM_ENTRIES:
            return meta

        meta["triggered"] = True
        entries_to_compress = history_output[:-MIN_VERBATIM_ENTRIES]
        entries_to_keep = history_output[-MIN_VERBATIM_ENTRIES:]

        meta["compressed_entries"] = len(entries_to_compress)
        meta["kept_verbatim"] = len(entries_to_keep)

        # Build the text block to summarise
        history_text = _build_history_text(entries_to_compress, _extract_text)

        if not history_text.strip():
            # Nothing meaningful to compress
            meta["triggered"] = False
            return meta

        # Call the utility model
        summary = await agent.call_utility_model(
            system=_build_summary_system_prompt(),
            message=_build_summary_message(history_text),
        )

        if not summary or not summary.strip():
            meta["error"] = "Utility model returned empty summary"
            return meta

        meta["summary_produced"] = True

        # Build a synthetic message object that history_output can carry.
        # Agent-Zero's history_output contains OutputMessage objects.
        # We create a plain dict-like wrapper that _extract_text can handle,
        # and that Agent-Zero's prompt assembly will render as a string.
        # We use a simple object with a .content attribute — the format
        # that _extract_text() already handles.
        class _SyntheticMessage:
            def __init__(self, content: str):
                self.content = content
                self.ai = False  # Render as human/system side

        synthetic = _SyntheticMessage(
            f"{COMPRESSION_LABEL}\n\n{summary.strip()}"
        )

        # Replace history_output in place
        loop_data.history_output = [synthetic] + entries_to_keep

        print(
            f"[Veda:HistoryCompressor] Compressed {len(entries_to_compress)} entries "
            f"→ 1 summary. Kept {len(entries_to_keep)} verbatim."
        )

    except Exception as e:
        meta["error"] = str(e)
        print(f"[Veda:HistoryCompressor] WARN: compression failed, history unchanged: {e}")

    return meta


async def compress_extras(agent, loop_data, model_name: str = "") -> dict:
    """
    Compress large entries in loop_data.extras_persistent using the utility model.

    Any individual extras_persistent value whose token count exceeds
    EXTRAS_COMPRESS_THRESHOLD is individually summarised and replaced.

    Returns metadata dict:
        {
            "entries_checked": int,
            "entries_compressed": int,
            "errors": list[str],
        }
    """
    meta = {
        "entries_checked": 0,
        "entries_compressed": 0,
        "errors": [],
    }

    try:
        _extract_text, _count_tokens_str, _get_tiktoken_encoder = _import_token_budget()
        encoder = _get_tiktoken_encoder(model_name) if model_name else None

        extras = getattr(loop_data, "extras_persistent", None)
        if not extras or not isinstance(extras, dict):
            return meta

        keys_to_compress = []
        for key, value in extras.items():
            text = _extract_text(value)
            token_count = _count_tokens_str(text, encoder)
            meta["entries_checked"] += 1
            if token_count > EXTRAS_COMPRESS_THRESHOLD:
                keys_to_compress.append((key, text, token_count))

        for key, text, original_tokens in keys_to_compress:
            try:
                summary = await agent.call_utility_model(
                    system=_build_extras_system_prompt(),
                    message=f"Compress this memory recall:\n\n{text}",
                )
                if summary and summary.strip():
                    extras[key] = f"{EXTRAS_LABEL}\n{summary.strip()}"
                    meta["entries_compressed"] += 1
                    print(
                        f"[Veda:ExtrasCompressor] Compressed extras['{key}'] "
                        f"{original_tokens} tokens → ~{len(summary)//4} tokens"
                    )
            except Exception as e:
                meta["errors"].append(f"extras['{key}']: {e}")
                print(f"[Veda:ExtrasCompressor] WARN: failed to compress extras['{key}']: {e}")

    except Exception as e:
        meta["errors"].append(f"outer: {e}")
        print(f"[Veda:ExtrasCompressor] WARN: outer failure: {e}")

    return meta
