import json
import os
from datetime import datetime, timezone
from python.helpers.extension import Extension

VEDA_STATE_DIR = "/a0/usr/veda-state"
AUDIT_DIR = os.path.join(VEDA_STATE_DIR, "audit")

# Escalation threshold — subordinate agents only
# Veda (agent 0) is exempt; she manages herself
ESCALATION_THRESHOLD = 10


class VedaEscalationCheck(Extension):
    """
    Fired at message_loop_end — after every loop iteration.
    Tracks iteration count for subordinate agents (agent number > 0).
    If iterations exceed ESCALATION_THRESHOLD, injects a structured
    escalation instruction into loop_data.extras_temporary.

    Veda (agent 0) is exempt — she has no superior to escalate to.
    Escalation is injected as a prompt instruction, not a hard stop.
    The agent must decide to use the response tool with escalation content.
    """

    async def execute(self, loop_data=None, **kwargs) -> None:
        if loop_data is None:
            return

        agent_number = self.agent.number

        # Veda is exempt from escalation
        if agent_number == 0:
            return

        iteration = getattr(loop_data, "iteration", 0)

        if iteration < ESCALATION_THRESHOLD:
            return

        # Threshold reached — inject escalation instruction
        agent_name = getattr(self.agent, "agent_name", "unknown")
        profile = getattr(self.agent.config, "profile", "unknown")
        current_spec = self.agent.get_data("current_spec_id") or "unknown"

        escalation_msg = (
            f"[ESCALATION REQUIRED] You have been running for {iteration} iterations "
            f"on Spec '{current_spec}'. This exceeds the maximum allowed threshold of "
            f"{ESCALATION_THRESHOLD} iterations. "
            f"You MUST stop and escalate to Veda immediately. "
            f"Use the response tool with the following structured report:\n"
            f"ESCALATION REPORT\n"
            f"Agent: {agent_name} (profile: {profile})\n"
            f"Spec: {current_spec}\n"
            f"Iterations: {iteration}\n"
            f"Reason: Exceeded iteration threshold — task may be stuck or too complex.\n"
            f"Last attempted action: [describe your last action]\n"
            f"Blocker: [describe what is preventing completion]\n"
            f"Recommendation: [what Veda should do next]"
        )

        if hasattr(loop_data, "extras_temporary"):
            loop_data.extras_temporary["veda_escalation"] = escalation_msg

        print(
            f"[Veda:Escalation] THRESHOLD REACHED: agent={agent_name} "
            f"profile={profile} spec={current_spec} iterations={iteration}"
        )

        # Write escalation event to audit log
        try:
            os.makedirs(AUDIT_DIR, exist_ok=True)
            now = datetime.now(timezone.utc)
            date_str = now.strftime("%Y-%m-%d")
            audit_file = os.path.join(AUDIT_DIR, f"{date_str}.audit.jsonl")
            entry = {
                "timestamp": now.isoformat(),
                "event_type": "escalation_triggered",
                "agent_name": agent_name,
                "agent_number": agent_number,
                "profile": profile,
                "spec_id": current_spec,
                "iterations": iteration,
                "threshold": ESCALATION_THRESHOLD,
            }
            with open(audit_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[Veda:Escalation] WARN: Failed to write escalation audit entry: {e}")
