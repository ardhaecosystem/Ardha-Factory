import json
import os
from datetime import datetime, timezone
from python.helpers.extension import Extension

VEDA_STATE_DIR = "/a0/usr/veda-state"
LOCKS_DIR = os.path.join(VEDA_STATE_DIR, "locks")
AUDIT_DIR = os.path.join(VEDA_STATE_DIR, "audit")
PIPELINE_STATE_FILE = os.path.join(VEDA_STATE_DIR, "pipeline_state.json")
RESTART_REQUIRED_FILE = os.path.join(VEDA_STATE_DIR, "restart_required.json")
LOCK_TTL_SECONDS = 3600


class VedaRehydrate(Extension):
    """
    Fired at agent_init — once on agent creation after restart.
    Runs at _30_ — after _20_load_registries.py, before any other init.

    Post-restart recovery tasks:
    1. Sweep expired locks from locks/ directory
    2. Re-queue interrupted specs (in-progress specs whose lock has expired)
    3. Clear the restart_required flag
    4. Update extension_mtimes baseline to current state
    5. Write restart recovery audit entry

    Only fires for Veda (agent 0).
    Subordinate agents have no recovery responsibilities.
    """

    async def execute(self, **kwargs) -> None:
        # Only Veda performs rehydration
        if self.agent.number != 0:
            return

        print("[Veda:Rehydrate] Post-restart rehydration starting...")

        expired_locks = self._sweep_expired_locks()
        requeued_specs = self._requeue_interrupted_specs(expired_locks)
        self._clear_restart_flag()
        self._update_extension_mtimes()
        self._audit_recovery(expired_locks, requeued_specs)

        print(
            f"[Veda:Rehydrate] Complete. "
            f"Expired locks swept: {len(expired_locks)}, "
            f"Specs re-queued: {len(requeued_specs)}"
        )

    def _sweep_expired_locks(self) -> list[dict]:
        """Remove expired lock files. Return list of expired lock metadata."""
        expired = []
        if not os.path.exists(LOCKS_DIR):
            return expired

        now_ts = datetime.now(timezone.utc).timestamp()
        for fname in os.listdir(LOCKS_DIR):
            if not fname.endswith(".lock.json"):
                continue
            path = os.path.join(LOCKS_DIR, fname)
            try:
                with open(path) as f:
                    lock = json.load(f)
                locked_at = lock.get("locked_at_ts", 0)
                ttl = lock.get("ttl_seconds", LOCK_TTL_SECONDS)
                if (now_ts - locked_at) > ttl:
                    expired.append(lock)
                    os.remove(path)
                    print(
                        f"[Veda:Rehydrate] Swept expired lock: "
                        f"{lock.get('spec_id')} (was held by {lock.get('locked_by')})"
                    )
            except (json.JSONDecodeError, OSError) as e:
                print(f"[Veda:Rehydrate] WARN: Could not process lock {fname}: {e}")

        return expired

    def _requeue_interrupted_specs(self, expired_locks: list[dict]) -> list[str]:
        """
        For each expired lock, check if the spec was in-progress.
        If so, move it back to the pipeline queue.
        """
        if not expired_locks:
            return []

        requeued = []
        pipeline = self._load_json(PIPELINE_STATE_FILE)
        if not pipeline:
            return requeued

        for lock in expired_locks:
            spec_id = lock.get("spec_id")
            if not spec_id:
                continue

            # If this spec was the current_spec or in queue, re-queue it
            current = pipeline.get("current_spec")
            if current == spec_id:
                pipeline["current_spec"] = None
                queue = pipeline.get("queue", [])
                if spec_id not in queue:
                    queue.insert(0, spec_id)  # Front of queue — highest priority
                    pipeline["queue"] = queue
                    requeued.append(spec_id)
                    print(f"[Veda:Rehydrate] Re-queued interrupted spec: {spec_id}")

        if requeued:
            pipeline["last_updated"] = datetime.now(timezone.utc).isoformat()
            pipeline["modified_by"] = "veda-rehydrate"
            self._save_json(PIPELINE_STATE_FILE, pipeline)

        return requeued

    def _clear_restart_flag(self) -> None:
        """Clear the restart_required flag after successful restart."""
        flag = self._load_json(RESTART_REQUIRED_FILE)
        if flag.get("required", False):
            flag["schema_version"] = "3.0.0"
            flag["required"] = False
            flag["cleared_at"] = datetime.now(timezone.utc).isoformat()
            flag["cleared_by"] = "veda-rehydrate"
            flag["reason"] = None
            flag["pending_changes"] = []
            self._save_json(RESTART_REQUIRED_FILE, flag)
            print("[Veda:Rehydrate] Restart required flag cleared.")

    def _update_extension_mtimes(self) -> None:
        """
        Capture current mtimes of all Veda extension files as new baseline.
        This prevents false-positive restart detection after a clean restart.
        """
        extensions_root = "/a0/usr/agents/veda/extensions"
        mtimes = {}

        if not os.path.exists(extensions_root):
            return

        for dirpath, dirnames, filenames in os.walk(extensions_root):
            for fname in filenames:
                if fname.endswith(".py") and not fname.startswith("__"):
                    full_path = os.path.join(dirpath, fname)
                    try:
                        mtimes[full_path] = os.path.getmtime(full_path)
                    except OSError:
                        pass

        if mtimes:
            mtimes["schema_version"] = "3.0.0"
            mtime_file = os.path.join(VEDA_STATE_DIR, "extension_mtimes.json")
            self._save_json(mtime_file, mtimes)
            print(f"[Veda:Rehydrate] Extension mtime baseline updated: {len(mtimes)} files.")

    def _audit_recovery(self, expired_locks: list, requeued_specs: list) -> None:
        try:
            os.makedirs(AUDIT_DIR, exist_ok=True)
            now = datetime.now(timezone.utc)
            date_str = now.strftime("%Y-%m-%d")
            audit_file = os.path.join(AUDIT_DIR, f"{date_str}.audit.jsonl")
            entry = {
                "timestamp": now.isoformat(),
                "event_type": "post_restart_rehydration",
                "agent_name": getattr(self.agent, "agent_name", "Veda"),
                "expired_locks_swept": len(expired_locks),
                "specs_requeued": requeued_specs,
                "expired_lock_details": [
                    {"spec_id": l.get("spec_id"), "held_by": l.get("locked_by")}
                    for l in expired_locks
                ],
            }
            with open(audit_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[Veda:Rehydrate] WARN: Audit write failed: {e}")

    def _load_json(self, path: str) -> dict:
        if not os.path.exists(path):
            return {}
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_json(self, path: str, data: dict) -> None:
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            print(f"[Veda:Rehydrate] WARN: Could not save {path}: {e}")
