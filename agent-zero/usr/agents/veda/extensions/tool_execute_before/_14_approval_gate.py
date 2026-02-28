import json
import os
from datetime import datetime, timezone
from python.helpers.extension import Extension

AUDIT_DIR = "/a0/usr/veda-state/audit"

# High-risk tool patterns requiring Veda approval
# Each entry: (tool_name, arg_key, pattern_substring)
# If tool_name matches AND arg content contains pattern → gate fires
HIGH_RISK_PATTERNS = [
    # Destructive file operations
    ("code_execution_tool", "code", "rm -rf"),
    ("code_execution_tool", "code", "rm -f /"),
    ("code_execution_tool", "code", "shutil.rmtree"),
    ("code_execution_tool", "code", "os.remove"),
    ("code_execution_tool", "code", "truncate"),
    # Git remote operations
    ("code_execution_tool", "code", "git push"),
    ("code_execution_tool", "code", "git push --force"),
    ("code_execution_tool", "code", "git reset --hard"),
    # Deployment operations
    ("code_execution_tool", "code", "docker compose up"),
    ("code_execution_tool", "code", "docker compose down"),
    ("code_execution_tool", "code", "systemctl restart"),
    ("code_execution_tool", "code", "systemctl stop"),
    # Sensitive file writes
    ("code_execution_tool", "code", "/etc/"),
    ("code_execution_tool", "code", "chmod 777"),
    ("code_execution_tool", "code", "chown root"),
    # Registry modification attempts by non-Veda agents
    ("code_execution_tool", "code", "veda-state/team_registry"),
    ("code_execution_tool", "code", "veda-state/project_registry"),
    ("code_execution_tool", "code", "veda-state/pipeline_state"),
]

# Tools that are always high-risk regardless of args
ALWAYS_HIGH_RISK_TOOLS = set()  # Reserved for future use


class VedaApprovalGate(Extension):
    """
    Fired at tool_execute_before — runs AFTER _12_git_validation.py.
    Intercepts high-risk operations by subordinate agents.

    If a high-risk pattern is detected:
    - Injects a STOP + escalation instruction into loop_data.extras_temporary
    - Audits the interception event
    - Does NOT modify tool_args (tool still runs — gate is advisory)

    NOTE: Making the gate a hard block (raising exception) would break
    Agent-Zero's tool execution flow. Advisory injection is the safe pattern —
    the agent sees the instruction on its next reasoning step and should stop.

    Veda (agent 0) is exempt — she has full authority.
    """

    async def execute(self, tool_args=None, tool_name=None, **kwargs) -> None:
        if not tool_name or not tool_args:
            return

        # Veda is exempt
        if self.agent.number == 0:
            return

        agent_name = getattr(self.agent, "agent_name", "unknown")
        profile = getattr(self.agent.config, "profile", "unknown")
        current_spec = self.agent.get_data("current_spec_id") or "unknown"

        # Check always-high-risk tools
        if tool_name in ALWAYS_HIGH_RISK_TOOLS:
            self._fire_gate(agent_name, profile, current_spec, tool_name, "always-high-risk", "")
            return

        # Check pattern-based rules
        for pattern_tool, arg_key, pattern in HIGH_RISK_PATTERNS:
            if tool_name != pattern_tool:
                continue
            arg_value = str(tool_args.get(arg_key, "")).lower()
            if pattern.lower() in arg_value:
                self._fire_gate(agent_name, profile, current_spec, tool_name, pattern, arg_value[:200])
                return  # First match is sufficient

    def _fire_gate(
        self,
        agent_name: str,
        profile: str,
        spec_id: str,
        tool_name: str,
        pattern: str,
        arg_preview: str,
    ) -> None:
        gate_msg = (
            f"[APPROVAL GATE] High-risk operation detected.\n"
            f"Tool: {tool_name}\n"
            f"Pattern matched: {pattern}\n"
            f"You are NOT authorised to perform this operation without Veda's explicit approval.\n"
            f"STOP immediately. Use the response tool to escalate to Veda with:\n"
            f"  - What operation you were about to perform\n"
            f"  - Why it is necessary for Spec '{spec_id}'\n"
            f"  - The exact command you intended to run\n"
            f"Wait for Veda to grant approval before proceeding."
        )

        # Inject into loop_data via the current loop_data on the agent
        loop_data = getattr(self.agent, "loop_data", None)
        if loop_data and hasattr(loop_data, "extras_temporary"):
            loop_data.extras_temporary["veda_approval_gate"] = gate_msg

        print(
            f"[Veda:ApprovalGate] INTERCEPTED: agent={agent_name} "
            f"profile={profile} spec={spec_id} tool={tool_name} pattern='{pattern}'"
        )

        # Audit the interception
        try:
            os.makedirs(AUDIT_DIR, exist_ok=True)
            now = datetime.now(timezone.utc)
            date_str = now.strftime("%Y-%m-%d")
            audit_file = os.path.join(AUDIT_DIR, f"{date_str}.audit.jsonl")
            entry = {
                "timestamp": now.isoformat(),
                "event_type": "approval_gate_triggered",
                "agent_name": agent_name,
                "agent_number": self.agent.number,
                "profile": profile,
                "spec_id": spec_id,
                "tool_name": tool_name,
                "pattern_matched": pattern,
                "arg_preview": arg_preview,
            }
            with open(audit_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[Veda:ApprovalGate] WARN: Audit write failed: {e}")
