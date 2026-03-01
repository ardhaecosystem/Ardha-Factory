"""
_15_tiered_summary.py
Ardha Factory — Phase 4C: Tiered Summary Injection
---------------------------------------------------
Extension hook: tool_execute_after

Fires after every tool execution. Intercepts call_subordinate results
and replaces large responses with tiered L0/L1/L2 summaries.

L0 (~200 tokens) is injected inline into Veda's context.
L1 (~500 tokens) and L2 (full) are written to files for on-demand retrieval.

Only active when:
- Agent profile is "veda"
- Tool name is "call_subordinate"
- Result exceeds TIER_THRESHOLD_TOKENS (300 tokens)

Fails open — any error leaves response.message completely untouched.
"""

from __future__ import annotations

import sys
from python.helpers.extension import Extension
from python.helpers.tool import Response

LIB_DIR = "/a0/usr/agents/veda/lib"


class VedaTieredSummary(Extension):

    async def execute(
        self,
        response: Response | None = None,
        tool_name: str = "",
        **kwargs,
    ) -> None:

        # Only intercept call_subordinate results
        if tool_name != "call_subordinate":
            return

        # Only active for Veda profile
        profile = getattr(self.agent.config, "profile", "")
        if profile != "veda":
            return

        if response is None or not response.message:
            return

        try:
            if LIB_DIR not in sys.path:
                sys.path.insert(0, LIB_DIR)
            from tier_builder import build_tiers

            context_id = getattr(self.agent.context, "id", "default")

            meta = await build_tiers(
                agent=self.agent,
                result=response.message,
                context_id=str(context_id),
            )

            if meta["tiered"] and meta["inline"]:
                response.message = meta["inline"]

                # Store tier metadata for audit extension
                loop_data = getattr(self.agent, "loop_data", None)
                if loop_data and hasattr(loop_data, "params_persistent"):
                    tier_events = loop_data.params_persistent.get(
                        "_tier_events", []
                    )
                    tier_events.append({
                        "tool_name": tool_name,
                        "original_tokens": meta["original_tokens"],
                        "l0_tokens": meta["l0_tokens"],
                        "l1_path": meta["l1_path"],
                        "l2_path": meta["l2_path"],
                        "error": meta["error"],
                    })
                    loop_data.params_persistent["_tier_events"] = tier_events

        except Exception as e:
            # Never crash — leave response untouched
            print(
                f"[Veda:TieredSummary] WARN: tiering failed, "
                f"original response preserved: {e}"
            )
