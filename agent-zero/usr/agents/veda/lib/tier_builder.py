"""
tier_builder.py
Ardha Factory — Phase 4C: Tiered Summary Injection
---------------------------------------------------
Utility library for building L0/L1/L2 tiered summaries of sub-agent results.

Placed at: /a0/usr/agents/veda/lib/tier_builder.py

Tiers:
  L0 — ~200 tokens. Injected inline into Veda's context. Always present.
       Contains: outcome, key decisions, artifacts created, blockers.
  L1 — ~500 tokens. Written to file. Retrieved on demand.
       Contains: full action sequence, all tool calls, error resolutions.
  L2 — Full compressed result. Written to file. Retrieved for deep inspection.
       Contains: complete sub-agent output, losslessly compressed.

Design decisions:
- Uses agent.call_utility_model() — same pattern as history.py
- Uses python.helpers.tokens.approximate_tokens() for exact counts
- L0 is always generated. L1/L2 only when result exceeds thresholds.
- Files written to /a0/usr/veda-state/tier-cache/{context_id}/
- Tier cache is ephemeral — not backed up, not part of governance state
- Fails open — on any error returns original result unmodified

No governance state writes. No FAISS operations.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Only tier results larger than this (tokens)
TIER_THRESHOLD_TOKENS = 300

# Target token budgets per tier
L0_MAX_TOKENS = 200
L1_MAX_TOKENS = 500

# Tier cache directory
TIER_CACHE_DIR = "/a0/usr/veda-state/tier-cache"

# Label injected into Veda's context with L0
TIER_HEADER = "[SUB-AGENT RESULT — TIERED SUMMARY]"
TIER_FOOTER_TEMPLATE = (
    "\n\n[Full details available on request: "
    "L1={l1_path} L2={l2_path}]"
)


# ---------------------------------------------------------------------------
# Summary prompts
# ---------------------------------------------------------------------------

def _l0_system_prompt() -> str:
    return (
        "You are a precise result summariser for an AI orchestration system.\n"
        "Produce an L0 summary (≤200 tokens) of a sub-agent's completed work.\n\n"
        "REQUIRED SECTIONS (include all that apply):\n"
        "1. OUTCOME: Did the task succeed or fail? One sentence.\n"
        "2. ARTIFACTS: Files created/modified/deleted (exact paths).\n"
        "3. DECISIONS: Key architectural or technical decisions made.\n"
        "4. BLOCKERS: Any unresolved issues or errors requiring attention.\n\n"
        "RULES:\n"
        "- Maximum 200 tokens. Be ruthlessly concise.\n"
        "- Never omit file paths, spec IDs, agent names, or error codes.\n"
        "- No preamble. Start directly with OUTCOME:\n"
    )


def _l0_message(result: str) -> str:
    return f"Summarise this sub-agent result into an L0 summary:\n\n{result}"


def _l1_system_prompt() -> str:
    return (
        "You are a precise result summariser for an AI orchestration system.\n"
        "Produce an L1 summary (≤500 tokens) of a sub-agent's completed work.\n\n"
        "INCLUDE:\n"
        "1. Full chronological action sequence (numbered list)\n"
        "2. Every tool call made and its outcome\n"
        "3. Every file path created, modified, or deleted\n"
        "4. Every error encountered and how it was resolved\n"
        "5. Final state of all modified resources\n\n"
        "RULES:\n"
        "- Maximum 500 tokens.\n"
        "- Preserve all IDs, paths, and technical values exactly.\n"
        "- No preamble. Start directly with the action sequence.\n"
    )


def _l1_message(result: str) -> str:
    return f"Summarise this sub-agent result into an L1 summary:\n\n{result}"


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------

def _tier_cache_path(context_id: str) -> Path:
    path = Path(TIER_CACHE_DIR) / context_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_tier_file(context_id: str, tier: str, content: str) -> str:
    """Write tier content to file. Returns absolute path."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    cache_dir = _tier_cache_path(context_id)
    filename = f"{tier}-{ts}.md"
    path = cache_dir / filename
    path.write_text(content, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def build_tiers(
    agent,
    result: str,
    context_id: str = "default",
) -> dict:
    """
    Build L0/L1/L2 tiers for a sub-agent result.

    Returns:
        {
            "tiered": bool,          # True if tiering was applied
            "l0": str,               # L0 summary text (always present if tiered)
            "l1_path": str | None,   # Path to L1 file
            "l2_path": str | None,   # Path to L2 file
            "inline": str,           # What to inject into Veda's context
            "original_tokens": int,
            "l0_tokens": int,
            "error": str | None,
        }
    """
    meta = {
        "tiered": False,
        "l0": "",
        "l1_path": None,
        "l2_path": None,
        "inline": result,           # Default: return original unmodified
        "original_tokens": 0,
        "l0_tokens": 0,
        "error": None,
    }

    try:
        # Use heuristic token estimation — tiktoken not reliably available
        # at /a0/usr/ extension load time. Chars ÷ 4 is accurate enough
        # for tiering decisions at the 300-token threshold.
        def approximate_tokens(text: str) -> int:
            return max(1, len(text) // 4)

        
        original_tokens = approximate_tokens(result)
        meta["original_tokens"] = original_tokens

        # Only tier if result is large enough to warrant it
        if original_tokens <= TIER_THRESHOLD_TOKENS:
            return meta

        meta["tiered"] = True

        # --- Generate L0 (inline summary) ---
        l0 = await agent.call_utility_model(
            system=_l0_system_prompt(),
            message=_l0_message(result),
        )

        if not l0 or not l0.strip():
            meta["error"] = "L0 generation returned empty"
            meta["tiered"] = False
            return meta

        meta["l0"] = l0.strip()
        meta["l0_tokens"] = approximate_tokens(l0)

        # --- Write L1 (detailed summary) ---
        try:
            l1 = await agent.call_utility_model(
                system=_l1_system_prompt(),
                message=_l1_message(result),
            )
            if l1 and l1.strip():
                l1_path = _write_tier_file(context_id, "L1", l1.strip())
                meta["l1_path"] = l1_path
        except Exception as e:
            print(f"[Veda:TierBuilder] WARN: L1 generation failed: {e}")

        # --- Write L2 (full compressed result) ---
        try:
            l2_path = _write_tier_file(context_id, "L2", result)
            meta["l2_path"] = l2_path
        except Exception as e:
            print(f"[Veda:TierBuilder] WARN: L2 write failed: {e}")

        # --- Assemble inline content for Veda's context ---
        footer = TIER_FOOTER_TEMPLATE.format(
            l1_path=meta["l1_path"] or "unavailable",
            l2_path=meta["l2_path"] or "unavailable",
        )
        meta["inline"] = f"{TIER_HEADER}\n\n{meta['l0']}{footer}"

        print(
            f"[Veda:TierBuilder] Tiered sub-agent result: "
            f"{original_tokens} tokens → {meta['l0_tokens']} tokens L0 "
            f"({round((1 - meta['l0_tokens']/original_tokens)*100)}% reduction)"
        )

    except Exception as e:
        meta["error"] = str(e)
        meta["tiered"] = False
        print(f"[Veda:TierBuilder] WARN: tiering failed, returning original: {e}")

    return meta
