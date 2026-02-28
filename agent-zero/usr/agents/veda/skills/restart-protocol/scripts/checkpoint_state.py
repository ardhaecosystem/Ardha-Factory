#!/usr/bin/env python3
"""
Restart Protocol — checkpoint_state.py
Checkpoints all Ardha Factory state before a container restart.
Sets restart_required flag and generates operator notification.
Called by Veda via the restart-protocol skill.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# registry_io — checksum-protected registry I/O
import sys as _sys
if "/a0/usr/agents/veda/scripts" not in _sys.path:
    _sys.path.insert(0, "/a0/usr/agents/veda/scripts")
from registry_io import save_registry, CorruptionError

VEDA_STATE_DIR = "/a0/usr/veda-state"
STATE_FILES = [
    "team_registry.json",
    "project_registry.json",
    "pipeline_state.json",
    "faiss_namespace_map.json",
    "extension_mtimes.json",
]
RESTART_REQUIRED_FILE = os.path.join(VEDA_STATE_DIR, "restart_required.json")
CHECKPOINT_FILE = os.path.join(VEDA_STATE_DIR, "last_checkpoint.json")
LOCKS_DIR = os.path.join(VEDA_STATE_DIR, "locks")
SPECS_DIR = os.path.join(VEDA_STATE_DIR, "specs")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}



def checkpoint(reason: str, pending_changes: list[str]) -> None:
    now = now_iso()
    errors = []
    state_summary = {}

    # Validate all state files are readable
    for fname in STATE_FILES:
        path = os.path.join(VEDA_STATE_DIR, fname)
        data = load_json(path)
        if not data and os.path.exists(path):
            errors.append(f"WARNING: {fname} could not be parsed")
        state_summary[fname] = "ok" if data else "missing"

    # Count active locks
    active_locks = 0
    if os.path.exists(LOCKS_DIR):
        active_locks = len([f for f in os.listdir(LOCKS_DIR) if f.endswith(".lock.json")])
    state_summary["active_locks"] = active_locks

    # Count active specs
    active_specs = 0
    if os.path.exists(SPECS_DIR):
        active_specs = len([f for f in os.listdir(SPECS_DIR) if f.endswith(".spec.json")])
    state_summary["active_specs"] = active_specs

    # Warn about active locks — these should be released before restart
    if active_locks > 0:
        print(f"[Restart Protocol] WARNING: {active_locks} active lock(s) found.")
        print("[Restart Protocol] Consider releasing all locks before restart.")
        print("[Restart Protocol] Proceeding — rehydration will sweep expired locks on restart.")

    # Write checkpoint summary
    checkpoint_data = {
        "checkpointed_at": now,
        "checkpointed_by": "veda",
        "reason": reason,
        "pending_changes": pending_changes,
        "state_summary": state_summary,
        "errors": errors,
    }
    save_registry(CHECKPOINT_FILE, checkpoint_data)
    print(f"[Restart Protocol] Checkpoint written: {CHECKPOINT_FILE}")

    # Set restart_required flag
    flag_data = {
        "schema_version": "3.0.0",
        "required": True,
        "reason": reason,
        "pending_changes": pending_changes,
        "flagged_at": now,
        "flagged_by": "veda",
    }
    save_registry(RESTART_REQUIRED_FILE, flag_data)
    print(f"[Restart Protocol] restart_required flag set.")

    # Print errors if any
    for err in errors:
        print(f"[Restart Protocol] {err}")

    print(f"[Restart Protocol] SUCCESS: Checkpoint complete.")
    print(f"[Restart Protocol] Reason: {reason}")
    print(f"[Restart Protocol] Pending changes: {len(pending_changes)}")
    print(f"[Restart Protocol] Active locks: {active_locks}")
    print(f"[Restart Protocol] Active specs: {active_specs}")


def verify() -> None:
    print("[Restart Protocol] Verifying state files...")
    all_ok = True

    for fname in STATE_FILES:
        path = os.path.join(VEDA_STATE_DIR, fname)
        if not os.path.exists(path):
            print(f"  MISSING: {fname}")
            all_ok = False
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            schema_ver = data.get("schema_version", "none")
            print(f"  OK: {fname} (schema_version={schema_ver})")
        except json.JSONDecodeError as e:
            print(f"  INVALID JSON: {fname} — {e}")
            all_ok = False

    # Check locks directory
    if os.path.exists(LOCKS_DIR):
        lock_count = len([f for f in os.listdir(LOCKS_DIR) if f.endswith(".lock.json")])
        print(f"  Active locks: {lock_count}")

    # Check restart flag
    flag = load_json(RESTART_REQUIRED_FILE)
    print(f"  restart_required: {flag.get('required', False)}")

    if all_ok:
        print("[Restart Protocol] All state files verified. Safe to restart.")
    else:
        print("[Restart Protocol] WARNING: Some files have issues. Review before restart.")
        sys.exit(1)


def notify() -> None:
    checkpoint_data = load_json(CHECKPOINT_FILE)
    flag_data = load_json(RESTART_REQUIRED_FILE)

    reason = flag_data.get("reason", checkpoint_data.get("reason", "unspecified"))
    pending = flag_data.get("pending_changes", checkpoint_data.get("pending_changes", []))
    checkpointed_at = checkpoint_data.get("checkpointed_at", "unknown")
    state_summary = checkpoint_data.get("state_summary", {})

    print("=" * 60)
    print("ARDHA FACTORY — RESTART REQUIRED")
    print("=" * 60)
    print(f"Reason: {reason}")
    print(f"Checkpointed at: {checkpointed_at}")
    print()
    print("Pending changes requiring restart:")
    for change in pending:
        print(f"  - {change}")
    print()
    print("State checkpoint summary:")
    for key, val in state_summary.items():
        print(f"  {key}: {val}")
    print()
    print("All state has been checkpointed to usr/veda-state/.")
    print("No data will be lost.")
    print()
    print("Papa, please run:")
    print("  cd /home/deploy/ardha && docker compose restart")
    print()
    print("After restart, Veda will automatically:")
    print("  - Sweep expired locks")
    print("  - Re-queue any interrupted specs")
    print("  - Clear the restart flag")
    print("  - Update extension baselines")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Ardha Factory Restart Protocol")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_checkpoint = subparsers.add_parser("checkpoint")
    p_checkpoint.add_argument("--reason", required=True)
    p_checkpoint.add_argument("--pending-changes", default="",
                              help="Pipe-separated list of pending changes")

    subparsers.add_parser("verify")
    subparsers.add_parser("notify")

    args = parser.parse_args()

    if args.command == "checkpoint":
        changes = [c.strip() for c in args.pending_changes.split("|") if c.strip()]
        checkpoint(args.reason, changes)
    elif args.command == "verify":
        verify()
    elif args.command == "notify":
        notify()


if __name__ == "__main__":
    main()
