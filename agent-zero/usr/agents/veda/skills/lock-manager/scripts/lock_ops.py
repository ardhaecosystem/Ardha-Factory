#!/usr/bin/env python3
"""
Lock Manager — lock_ops.py
Spec-level mutex locking for the Ardha Factory.
Uses atomic file write-then-rename for lock safety.
Called by Veda via the lock-manager skill.
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

# registry_io — checksum-protected registry I/O
import sys as _sys
if "/a0/usr/agents/veda/scripts" not in _sys.path:
    _sys.path.insert(0, "/a0/usr/agents/veda/scripts")
from registry_io import save_registry, CorruptionError


VEDA_STATE_DIR = "/a0/usr/veda-state"
LOCKS_DIR = os.path.join(VEDA_STATE_DIR, "locks")
LOCK_TTL_SECONDS = 3600  # 1 hour default


# --- Helpers ---

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def lock_path(spec_id: str) -> str:
    # Sanitise spec_id for safe filename
    safe = spec_id.replace("/", "-").replace("\\", "-").replace(" ", "-")
    return os.path.join(LOCKS_DIR, f"{safe}.lock.json")


def load_lock(spec_id: str) -> dict | None:
    path = lock_path(spec_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def is_expired(lock: dict) -> bool:
    locked_at = lock.get("locked_at_ts", 0)
    ttl = lock.get("ttl_seconds", LOCK_TTL_SECONDS)
    return (now_ts() - locked_at) > ttl


def write_lock_atomic(spec_id: str, data: dict) -> None:
    """
    Atomic write using write-to-temp + os.rename().
    os.rename() is atomic on POSIX filesystems — prevents partial writes.
    """
    path = lock_path(spec_id)
    dir_ = os.path.dirname(path)
    os.makedirs(dir_, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(__import__("json").dumps(data, indent=2))
        os.rename(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def delete_lock(spec_id: str) -> None:
    path = lock_path(spec_id)
    if os.path.exists(path):
        os.remove(path)


# --- Operations ---

def acquire(spec_id: str, agent_id: str, team_id: str, project_id: str) -> None:
    existing = load_lock(spec_id)

    if existing:
        if not is_expired(existing):
            holder = existing.get("locked_by")
            if holder == agent_id:
                print(f"[Lock Manager] INFO: Agent '{agent_id}' already holds lock for '{spec_id}'.")
                return
            print(f"[Lock Manager] ERROR: Spec '{spec_id}' is locked by '{holder}'.")
            print(f"[Lock Manager] Lock expires at: {existing.get('expires_at')}")
            print(f"[Lock Manager] Cannot acquire — another agent holds this lock.")
            sys.exit(1)
        else:
            print(f"[Lock Manager] INFO: Existing lock for '{spec_id}' has expired. Reclaiming.")

    ts = now_ts()
    expires_ts = ts + LOCK_TTL_SECONDS
    expires_dt = datetime.fromtimestamp(expires_ts, tz=timezone.utc).isoformat()

    lock_data = {
        "spec_id": spec_id,
        "locked_by": agent_id,
        "team_id": team_id,
        "project_id": project_id,
        "locked_at": now_iso(),
        "locked_at_ts": ts,
        "ttl_seconds": LOCK_TTL_SECONDS,
        "expires_at": expires_dt,
        "status": "locked"
    }

    write_lock_atomic(spec_id, lock_data)
    print(f"[Lock Manager] SUCCESS: Lock acquired for '{spec_id}'.")
    print(f"[Lock Manager] Holder: {agent_id} | Team: {team_id} | Project: {project_id}")
    print(f"[Lock Manager] Expires: {expires_dt}")


def release(spec_id: str, agent_id: str) -> None:
    existing = load_lock(spec_id)

    if not existing:
        print(f"[Lock Manager] INFO: No lock exists for '{spec_id}'. Nothing to release.")
        return

    holder = existing.get("locked_by")
    if holder != agent_id:
        if is_expired(existing):
            print(f"[Lock Manager] INFO: Lock for '{spec_id}' was held by '{holder}' but has expired. Cleaning up.")
            delete_lock(spec_id)
            return
        print(f"[Lock Manager] ERROR: Cannot release lock for '{spec_id}'.")
        print(f"[Lock Manager] Lock is held by '{holder}', not '{agent_id}'.")
        sys.exit(1)

    delete_lock(spec_id)
    print(f"[Lock Manager] SUCCESS: Lock released for '{spec_id}'.")
    print(f"[Lock Manager] Released by: {agent_id}")


def check(spec_id: str) -> None:
    existing = load_lock(spec_id)

    if not existing:
        print(f"[Lock Manager] Spec '{spec_id}': UNLOCKED — available for dispatch.")
        return

    if is_expired(existing):
        print(f"[Lock Manager] Spec '{spec_id}': EXPIRED lock (was held by '{existing.get('locked_by')}').")
        print(f"[Lock Manager] Lock is reclaimable.")
        return

    holder = existing.get("locked_by")
    expires = existing.get("expires_at")
    team = existing.get("team_id")
    project = existing.get("project_id")
    print(f"[Lock Manager] Spec '{spec_id}': LOCKED")
    print(f"[Lock Manager] Holder: {holder} | Team: {team} | Project: {project}")
    print(f"[Lock Manager] Expires: {expires}")


def cleanup() -> None:
    if not os.path.exists(LOCKS_DIR):
        print("[Lock Manager] Locks directory does not exist. Nothing to clean.")
        return

    lock_files = [f for f in os.listdir(LOCKS_DIR) if f.endswith(".lock.json")]
    if not lock_files:
        print("[Lock Manager] No lock files found.")
        return

    cleaned = 0
    active = 0
    for fname in lock_files:
        path = os.path.join(LOCKS_DIR, fname)
        try:
            with open(path) as f:
                lock = json.load(f)
            if is_expired(lock):
                os.remove(path)
                print(f"[Lock Manager] Cleaned expired lock: {fname} (was held by '{lock.get('locked_by')}')")
                cleaned += 1
            else:
                active += 1
        except (json.JSONDecodeError, OSError) as e:
            print(f"[Lock Manager] WARN: Could not process {fname}: {e}")

    print(f"[Lock Manager] Cleanup complete. Removed: {cleaned}, Active: {active}")


def list_locks() -> None:
    if not os.path.exists(LOCKS_DIR):
        print("[Lock Manager] No locks directory.")
        return

    lock_files = [f for f in os.listdir(LOCKS_DIR) if f.endswith(".lock.json")]
    if not lock_files:
        print("[Lock Manager] No active locks.")
        return

    print(f"[Lock Manager] Locks ({len(lock_files)} total):")
    for fname in sorted(lock_files):
        path = os.path.join(LOCKS_DIR, fname)
        try:
            with open(path) as f:
                lock = json.load(f)
            expired = is_expired(lock)
            status = "EXPIRED" if expired else "ACTIVE"
            print(f"  [{status}] {lock.get('spec_id')} — holder={lock.get('locked_by')}, expires={lock.get('expires_at')}")
        except (json.JSONDecodeError, OSError):
            print(f"  [ERROR] {fname} — could not parse")


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Ardha Factory Lock Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_acquire = subparsers.add_parser("acquire")
    p_acquire.add_argument("--spec-id", required=True)
    p_acquire.add_argument("--agent-id", required=True)
    p_acquire.add_argument("--team-id", required=True)
    p_acquire.add_argument("--project-id", required=True)

    p_release = subparsers.add_parser("release")
    p_release.add_argument("--spec-id", required=True)
    p_release.add_argument("--agent-id", required=True)

    p_check = subparsers.add_parser("check")
    p_check.add_argument("--spec-id", required=True)

    subparsers.add_parser("cleanup")
    subparsers.add_parser("list")

    args = parser.parse_args()

    if args.command == "acquire":
        acquire(args.spec_id, args.agent_id, args.team_id, args.project_id)
    elif args.command == "release":
        release(args.spec_id, args.agent_id)
    elif args.command == "check":
        check(args.spec_id)
    elif args.command == "cleanup":
        cleanup()
    elif args.command == "list":
        list_locks()


if __name__ == "__main__":
    main()
