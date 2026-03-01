import json
import os
from datetime import datetime, timezone
from python.helpers.extension import Extension

VEDA_STATE_DIR = "/a0/usr/veda-state"
AUDIT_DIR = os.path.join(VEDA_STATE_DIR, "audit")

# Tools that are too noisy to log at full detail
SKIP_TOOLS = {"response"}

# High-risk tools flagged in audit
HIGH_RISK_TOOLS = {
    "code_execution_tool",
    "browser_agent",
    "veda_dispatch",
}


class VedaAuditTool(Extension):
    """
    Fired at tool_execute_after — after every tool execution.
    Appends a structured JSONL entry to the daily audit log.
    For call_subordinate, also flushes Phase 4C tier events.

    Captures: tool name, agent, spec context, success/failure, response length.
    Never logs full response content — only metadata.
    Audit log failure never crashes the agent.
    """

    async def execute(self, response=None, tool_name=None, **kwargs) -> None:
        try:
            if not tool_name or tool_name in SKIP_TOOLS:
                return

            os.makedirs(AUDIT_DIR, exist_ok=True)

            now = datetime.now(timezone.utc)
            date_str = now.strftime("%Y-%m-%d")
            audit_file = os.path.join(AUDIT_DIR, f"{date_str}.audit.jsonl")

            agent_name = getattr(self.agent, "agent_name", "unknown")
            agent_number = getattr(self.agent, "number", -1)
            profile = getattr(self.agent.config, "profile", "unknown")
            current_spec = self.agent.get_data("current_spec_id") or None

            # Response metadata — never full content
            response_len = 0
            break_loop = False
            if response:
                response_len = len(getattr(response, "message", "") or "")
                break_loop = getattr(response, "break_loop", False)

            entry = {
                "timestamp": now.isoformat(),
                "event_type": "tool_execute",
                "agent_name": agent_name,
                "agent_number": agent_number,
                "profile": profile,
                "spec_id": current_spec,
                "tool_name": tool_name,
                "high_risk": tool_name in HIGH_RISK_TOOLS,
                "response_length": response_len,
                "break_loop": break_loop,
            }

            with open(audit_file, "a") as f:
                f.write(json.dumps(entry) + "\n")

            # --- Flush Phase 4C tier events for call_subordinate ---
            if tool_name == "call_subordinate":
                loop_data = getattr(self.agent, "loop_data", None)
                if loop_data and hasattr(loop_data, "params_persistent"):
                    tier_events = loop_data.params_persistent.pop(
                        "_tier_events", []
                    )
                    for event in tier_events:
                        tier_entry = {
                            "timestamp": now.isoformat(),
                            "event_type": "subordinate_tiered",
                            "agent_name": agent_name,
                            "agent_number": agent_number,
                            "profile": profile,
                            "spec_id": current_spec,
                            "tool_name": tool_name,
                            "original_tokens": event.get("original_tokens", 0),
                            "l0_tokens": event.get("l0_tokens", 0),
                            "l1_path": event.get("l1_path"),
                            "l2_path": event.get("l2_path"),
                            "error": event.get("error"),
                        }
                        with open(audit_file, "a") as f:
                            f.write(json.dumps(tier_entry) + "\n")

                    if tier_events:
                        print(
                            f"[Veda:AuditTool] Flushed {len(tier_events)} "
                            f"tier event(s) to audit log"
                        )

        except Exception as e:
            print(f"[Veda:AuditTool] WARN: Failed to write tool audit entry: {e}")
