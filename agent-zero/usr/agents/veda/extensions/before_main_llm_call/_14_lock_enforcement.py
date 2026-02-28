import json
import os
from datetime import datetime, timezone
from python.helpers.extension import Extension

VEDA_STATE_DIR = "/a0/usr/veda-state"
LOCKS_DIR = os.path.join(VEDA_STATE_DIR, "locks")
LOCK_TTL_SECONDS = 3600


class VedaLockEnforcement(Extension):
    """
    Fired before every LLM call (before_main_llm_call hook).
    Runs AFTER _12_team_isolation.py (numeric order: _14_ > _12_).

    For Veda (agent 0): injects a reminder of the lock-before-dispatch invariant.
    For subordinate agents: checks if the agent holds a valid lock for its
    current Spec. If not, injects a STOP instruction into extras_temporary.

    This is a soft enforcement — it injects a strong instruction into the prompt.
    Hard enforcement lives in the veda_dispatch tool which checks locks before
    creating subordinates.
    """

    async def execute(self, loop_data=None, **kwargs) -> None:
        if loop_data is None:
            return

        agent_number = self.agent.number

        # --- Veda (agent 0) — inject lock invariant reminder ---
        if agent_number == 0:
            if hasattr(loop_data, "extras_temporary"):
                loop_data.extras_temporary["veda_lock_reminder"] = (
                    "[LOCK INVARIANT] Before dispatching any Spec: "
                    "(1) verify spec hash via spec-manager, "
                    "(2) acquire mutex lock via lock-manager, "
                    "(3) then dispatch via veda_dispatch tool. "
                    "Never dispatch without a verified hash and an active lock."
                )
            return

        # --- Subordinate agents — check lock ownership ---
        agent_name = getattr(self.agent.config, "profile", None)
        if not agent_name:
            return

        # Find which spec this agent is working on from its context
        current_spec = self.agent.get_data("current_spec_id")
        if not current_spec:
            # Agent has no spec assigned — no lock check needed
            return

        lock = self._load_lock(current_spec)

        if not lock:
            if hasattr(loop_data, "extras_temporary"):
                loop_data.extras_temporary["veda_lock_warning"] = (
                    f"[LOCK WARNING] No lock found for Spec '{current_spec}'. "
                    f"You should not be executing this Spec without a valid lock. "
                    f"Stop and report this anomaly to Veda immediately."
                )
            print(f"[Veda:LockCheck] WARN: No lock for spec={current_spec} agent={agent_name}")
            return

        if self._is_expired(lock):
            if hasattr(loop_data, "extras_temporary"):
                loop_data.extras_temporary["veda_lock_warning"] = (
                    f"[LOCK EXPIRED] Your lock for Spec '{current_spec}' has expired. "
                    f"Stop execution immediately and report to Veda. "
                    f"Do not continue until Veda re-acquires the lock."
                )
            print(f"[Veda:LockCheck] WARN: Expired lock for spec={current_spec} agent={agent_name}")
            return

        holder = lock.get("locked_by")
        if holder != agent_name:
            if hasattr(loop_data, "extras_temporary"):
                loop_data.extras_temporary["veda_lock_warning"] = (
                    f"[LOCK VIOLATION] Spec '{current_spec}' lock is held by '{holder}', "
                    f"not by you ('{agent_name}'). "
                    f"Stop immediately. Report this conflict to Veda."
                )
            print(f"[Veda:LockCheck] ERROR: Lock holder mismatch spec={current_spec} "
                  f"holder={holder} agent={agent_name}")
            return

        # Lock is valid — inject confirmation
        expires = lock.get("expires_at", "unknown")
        if hasattr(loop_data, "extras_temporary"):
            loop_data.extras_temporary["veda_lock_status"] = (
                f"[LOCK OK] You hold a valid lock for Spec '{current_spec}'. "
                f"Lock expires: {expires}. Proceed with your assigned task."
            )

    def _load_lock(self, spec_id: str) -> dict | None:
        safe = spec_id.replace("/", "-").replace("\\", "-").replace(" ", "-")
        path = os.path.join(LOCKS_DIR, f"{safe}.lock.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _is_expired(self, lock: dict) -> bool:
        locked_at = lock.get("locked_at_ts", 0)
        ttl = lock.get("ttl_seconds", LOCK_TTL_SECONDS)
        now = datetime.now(timezone.utc).timestamp()
        return (now - locked_at) > ttl
