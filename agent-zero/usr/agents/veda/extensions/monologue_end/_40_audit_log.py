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

            # Count iterations from loop_data
            iteration = 0
            if loop_data and hasattr(loop_data, "iteration"):
                iteration = loop_data.iteration

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

        except Exception as e:
            # Audit log failure must NEVER crash the agent
            print(f"[Veda:AuditLog] WARN: Failed to write monologue audit entry: {e}")
