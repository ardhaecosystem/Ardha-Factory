import json
import os
from datetime import datetime, timezone
from python.helpers.extension import Extension

VEDA_STATE_DIR = "/a0/usr/veda-state"
AUDIT_DIR = os.path.join(VEDA_STATE_DIR, "audit")


class VedaAuditLog(Extension):
    """
    Fired at monologue_end — after every completed agent monologue.
    Appends a structured JSONL entry to the daily audit log.
    Also flushes Phase 4A compression events from params_persistent.

    The audit log is NEVER written to FAISS.
    It is append-only plain file to ensure integrity.
    Files rotate daily by date in filename.
    """

    async def execute(self, loop_data=None, **kwargs) -> None:
        try:
            os.makedirs(AUDIT_DIR, exist_ok=True)

            now = datetime.now(timezone.utc)
            date_str = now.strftime("%Y-%m-%d")
            audit_file = os.path.join(AUDIT_DIR, f"{date_str}.audit.jsonl")

            agent_name = getattr(self.agent, "agent_name", "unknown")
            agent_number = getattr(self.agent, "number", -1)
            profile = getattr(self.agent.config, "profile", "unknown")
            memory_subdir = getattr(self.agent.config, "memory_subdir", "unknown")
            current_spec = self.agent.get_data("current_spec_id") or None

            iteration = 0
            if loop_data and hasattr(loop_data, "iteration"):
                iteration = loop_data.iteration

            # --- Main monologue_end entry ---
            entry = {
                "timestamp": now.isoformat(),
                "event_type": "monologue_end",
                "agent_name": agent_name,
                "agent_number": agent_number,
                "profile": profile,
                "memory_subdir": memory_subdir,
                "spec_id": current_spec,
                "iterations": iteration,
            }

            with open(audit_file, "a") as f:
                f.write(json.dumps(entry) + "\n")

            # --- Flush Phase 4A compression events ---
            if loop_data and hasattr(loop_data, "params_persistent"):
                compression_events = loop_data.params_persistent.pop(
                    "_compression_events", []
                )
                for event in compression_events:
                    compression_entry = {
                        "timestamp": event.get("timestamp", now.isoformat()),
                        "event_type": "context_compression",
                        "agent_name": agent_name,
                        "agent_number": agent_number,
                        "profile": profile,
                        "spec_id": current_spec,
                        "iteration": event.get("iteration", -1),
                        "tokens_before": event.get("tokens_before", 0),
                        "tokens_after": event.get("tokens_after", 0),
                        "tokens_saved": event.get("tokens_saved", 0),
                        "history_compressed": event.get(
                            "history_meta", {}
                        ).get("summary_produced", False),
                        "extras_compressed": event.get(
                            "extras_meta", {}
                        ).get("entries_compressed", 0),
                        "error": event.get("history_meta", {}).get("error"),
                    }
                    with open(audit_file, "a") as f:
                        f.write(json.dumps(compression_entry) + "\n")

                if compression_events:
                    print(
                        f"[Veda:AuditLog] Flushed {len(compression_events)} "
                        f"compression event(s) to audit log"
                    )

        except Exception as e:
            print(f"[Veda:AuditLog] WARN: Failed to write monologue audit entry: {e}")
