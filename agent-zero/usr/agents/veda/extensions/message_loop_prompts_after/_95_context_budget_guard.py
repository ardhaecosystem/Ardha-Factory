"""
_95_context_budget_guard.py
Ardha Factory — Phase 4A: Runtime Context Budget Guard
-------------------------------------------------------
Extension hook: message_loop_prompts_after

Fires after ALL core extensions complete (memory recall, skills, agent info).
Runs before the final prompt is assembled and sent to the LLM.

Responsibilities:
- Estimate total token count of the assembled context
- If over threshold: compress history and oversized extras_persistent entries
- Inject a budget status line into extras_temporary for observability
- Record compression metadata in params_persistent for the audit extension

Safety rules:
- Only active when agent profile is "veda"
- Never modifies system prompt
- Never modifies extras_temporary (except adding our own status key)
- Never touches governance state files
- Fails open — any error leaves context completely untouched

Trigger: 85% of available context window (ctx_length - 4096 response buffer)
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone

from python.helpers.extension import Extension

LIB_DIR = "/a0/usr/agents/veda/lib"


def _import_libs():
    """Lazy import of Phase 4A lib modules."""
    if LIB_DIR not in sys.path:
        sys.path.insert(0, LIB_DIR)
    from token_budget import get_budget_status
    from history_compressor import compress_history, compress_extras
    return get_budget_status, compress_history, compress_extras


class VedaContextBudgetGuard(Extension):
    """
    Per-iteration context budget monitor and history compressor.

    Triggered every loop iteration via message_loop_prompts_after.
    Only compresses when token usage exceeds the configured threshold.
    """

    async def execute(self, loop_data=None, **kwargs) -> None:
        if loop_data is None:
            return

        # Only active for the Veda profile
        profile = getattr(self.agent.config, "profile", "")
        if profile != "veda":
            return

        try:
            get_budget_status, compress_history, compress_extras = _import_libs()

            # --- Read model config ---
            ctx_length = getattr(
                self.agent.config.chat_model, "ctx_length", 131072
            )
            model_name = getattr(
                self.agent.config.chat_model, "name", ""
            )

            # --- Estimate current token usage ---
            status = get_budget_status(
                loop_data=loop_data,
                ctx_length=ctx_length,
                model_name=model_name,
            )

            tokens = status["tokens"]
            utilisation = status["utilisation_pct"]
            over_budget = status["over_budget"]

            # --- Always inject observability line into extras_temporary ---
            if hasattr(loop_data, "extras_temporary"):
                loop_data.extras_temporary["_budget_status"] = (
                    f"[CONTEXT BUDGET] "
                    f"Total: {tokens['total']:,} tokens | "
                    f"Utilisation: {utilisation}% | "
                    f"Limit: {ctx_length:,} | "
                    f"{'⚠ COMPRESSING' if over_budget else '✓ OK'}"
                )

            # --- Log every iteration for visibility ---
            print(
                f"[Veda:BudgetGuard] iter={getattr(loop_data, 'iteration', '?')} "
                f"tokens={tokens['total']:,} "
                f"({utilisation}% of {ctx_length:,}) "
                f"system={tokens['system']:,} "
                f"extras={tokens['extras']:,} "
                f"history={tokens['history']:,} "
                f"{'→ TRIGGER' if over_budget else '→ OK'}"
            )

            if not over_budget:
                return

            # --- Budget exceeded — run compression ---
            print(
                f"[Veda:BudgetGuard] Budget threshold exceeded. "
                f"Compressing history and extras..."
            )

            history_meta = await compress_history(
                agent=self.agent,
                loop_data=loop_data,
                model_name=model_name,
            )

            extras_meta = await compress_extras(
                agent=self.agent,
                loop_data=loop_data,
                model_name=model_name,
            )

            # --- Re-estimate after compression ---
            status_after = get_budget_status(
                loop_data=loop_data,
                ctx_length=ctx_length,
                model_name=model_name,
            )
            tokens_after = status_after["tokens"]

            saved = tokens["total"] - tokens_after["total"]
            print(
                f"[Veda:BudgetGuard] Compression complete. "
                f"Before: {tokens['total']:,} | "
                f"After: {tokens_after['total']:,} | "
                f"Saved: {saved:,} tokens"
            )

            # --- Update observability line with post-compression status ---
            if hasattr(loop_data, "extras_temporary"):
                loop_data.extras_temporary["_budget_status"] = (
                    f"[CONTEXT BUDGET — COMPRESSED] "
                    f"Before: {tokens['total']:,} | "
                    f"After: {tokens_after['total']:,} | "
                    f"Saved: {saved:,} tokens | "
                    f"Utilisation: {status_after['utilisation_pct']}%"
                )

            # --- Store metadata in params_persistent for audit extension ---
            if hasattr(loop_data, "params_persistent"):
                compression_events = loop_data.params_persistent.get(
                    "_compression_events", []
                )
                compression_events.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "iteration": getattr(loop_data, "iteration", -1),
                    "tokens_before": tokens["total"],
                    "tokens_after": tokens_after["total"],
                    "tokens_saved": saved,
                    "history_meta": history_meta,
                    "extras_meta": extras_meta,
                })
                loop_data.params_persistent["_compression_events"] = compression_events

        except Exception as e:
            # Never crash the agent — log and continue
            print(f"[Veda:BudgetGuard] WARN: guard failed, context unchanged: {e}")
