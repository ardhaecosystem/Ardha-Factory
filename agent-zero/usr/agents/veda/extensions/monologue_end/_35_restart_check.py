import json
import os
from datetime import datetime, timezone
from python.helpers.extension import Extension

VEDA_STATE_DIR = "/a0/usr/veda-state"
RESTART_REQUIRED_FILE = os.path.join(VEDA_STATE_DIR, "restart_required.json")
EXTENSION_MTIMES_FILE = os.path.join(VEDA_STATE_DIR, "extension_mtimes.json")
AUDIT_DIR = os.path.join(VEDA_STATE_DIR, "audit")

# Only fire for Veda (agent 0) — subordinates don't manage restarts
# Only check every N monologues to avoid filesystem overhead on every response
CHECK_EVERY_N = 5


class VedaRestartCheck(Extension):
    """
    Fired at monologue_end — after every Veda monologue.
    Runs at _35_ — before _40_audit_log.py.

    Two checks:
    1. restart_required.json flag — set by Agent Forge or extension updates
    2. Extension mtime drift — detects if any extension files changed on disk
       since the baseline was captured (indicates restart needed to reload)

    If either check triggers, injects a high-priority restart notification
    into Veda's next prompt via agent.data so it appears on next activation.

    Only fires for Veda (agent 0). Checks every CHECK_EVERY_N monologues
    to reduce filesystem overhead.
    """

    async def execute(self, loop_data=None, **kwargs) -> None:
        # Only Veda manages restarts
        if self.agent.number != 0:
            return

        # Rate limit checks
        check_count = self.agent.get_data("_restart_check_count") or 0
        check_count += 1
        self.agent.set_data("_restart_check_count", check_count)

        if check_count % CHECK_EVERY_N != 0:
            return

        restart_needed = False
        reasons = []
        pending_changes = []

        # --- Check 1: restart_required.json flag ---
        flag = self._load_json(RESTART_REQUIRED_FILE)
        if flag.get("required", False):
            restart_needed = True
            reasons.append(flag.get("reason", "restart_required flag set"))
            pending_changes.extend(flag.get("pending_changes", []))

        # --- Check 2: Extension mtime drift ---
        baseline = self._load_json(EXTENSION_MTIMES_FILE)
        if baseline:
            drift = self._check_mtime_drift(baseline)
            if drift:
                restart_needed = True
                reasons.append("Extension files modified since last restart")
                pending_changes.extend(drift)

        if not restart_needed:
            return

        # --- Inject restart notification into Veda's next prompt ---
        restart_notice = (
            f"[RESTART REQUIRED]\n"
            f"Reason(s): {'; '.join(reasons)}\n"
            f"Pending changes:\n" +
            "\n".join(f"  - {c}" for c in pending_changes) +
            f"\n\nAll registry state is checkpointed to usr/veda-state/.\n"
            f"Please inform papa that a container restart is required.\n"
            f"Papa should run: cd /home/deploy/ardha && docker compose restart"
        )

        if loop_data and hasattr(loop_data, "extras_persistent"):
            loop_data.extras_persistent["veda_restart_notice"] = restart_notice

        print(f"[Veda:RestartCheck] RESTART REQUIRED: {'; '.join(reasons)}")

        # Audit the detection
        self._audit(reasons, pending_changes)

    def _check_mtime_drift(self, baseline: dict) -> list[str]:
        """Compare current extension mtimes against baseline. Return list of drifted files."""
        drifted = []
        for path, recorded_mtime in baseline.items():
            if not os.path.exists(path):
                continue
            current_mtime = os.path.getmtime(path)
            if abs(current_mtime - recorded_mtime) > 1.0:  # 1 second tolerance
                drifted.append(f"{path} (modified)")
        return drifted

    def _load_json(self, path: str) -> dict:
        if not os.path.exists(path):
            return {}
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _audit(self, reasons: list, pending_changes: list) -> None:
        try:
            os.makedirs(AUDIT_DIR, exist_ok=True)
            now = datetime.now(timezone.utc)
            date_str = now.strftime("%Y-%m-%d")
            audit_file = os.path.join(AUDIT_DIR, f"{date_str}.audit.jsonl")
            entry = {
                "timestamp": now.isoformat(),
                "event_type": "restart_required_detected",
                "agent_name": getattr(self.agent, "agent_name", "Veda"),
                "reasons": reasons,
                "pending_changes": pending_changes,
            }
            with open(audit_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[Veda:RestartCheck] WARN: Audit write failed: {e}")
