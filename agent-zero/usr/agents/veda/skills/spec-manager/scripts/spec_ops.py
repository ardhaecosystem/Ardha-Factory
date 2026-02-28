#!/usr/bin/env python3
"""
Spec Manager — spec_ops.py
Creates, hashes, verifies, and manages Specs for the Ardha Factory.
SHA-256 hash computed from spec_id + AC + tasks (immutable after creation).
Called by Veda via the spec-manager skill after papa's approval.
"""

import argparse
import hashlib
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
SPECS_DIR = os.path.join(VEDA_STATE_DIR, "specs")
PROJECT_REGISTRY_FILE = os.path.join(VEDA_STATE_DIR, "project_registry.json")

VALID_STATUSES = {"draft", "ready", "in-progress", "done", "failed"}


# --- Helpers ---

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def spec_path(spec_id: str) -> str:
    safe = spec_id.replace("/", "-").replace("\\", "-").replace(" ", "-")
    return os.path.join(SPECS_DIR, f"{safe}.spec.json")


def load_spec(spec_id: str) -> dict | None:
    path = spec_path(spec_id)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def save_spec(spec_id: str, data: dict) -> None:
    os.makedirs(SPECS_DIR, exist_ok=True)
    path = spec_path(spec_id)
    save_registry(path, data)


def compute_hash(spec_id: str, acceptance_criteria: list[str], tasks: list[str]) -> str:
    """
    Compute SHA-256 hash of immutable spec content.
    Inputs: spec_id + sorted/normalised AC lines + sorted/normalised task lines.
    Status and dev notes are excluded — only AC and tasks are immutable.
    """
    normalised_ac = sorted([line.strip() for line in acceptance_criteria if line.strip()])
    normalised_tasks = sorted([line.strip() for line in tasks if line.strip()])
    content = spec_id + "|".join(normalised_ac) + "|".join(normalised_tasks)
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_project_registry() -> dict:
    if not os.path.exists(PROJECT_REGISTRY_FILE):
        return {}
    with open(PROJECT_REGISTRY_FILE) as f:
        return json.load(f)


def save_project_registry(data: dict) -> None:
    with open(PROJECT_REGISTRY_FILE, "w") as f:
        json.dump(data, f, indent=2)


# --- Operations ---

def create(
    spec_id: str,
    title: str,
    project_id: str,
    team_id: str,
    agent_id: str,
    acceptance_criteria: list[str],
    tasks: list[str]
) -> None:
    # Check not already exists
    if load_spec(spec_id):
        print(f"[Spec Manager] ERROR: Spec '{spec_id}' already exists.")
        sys.exit(1)

    # Validate AC and tasks not empty
    ac_clean = [line.strip() for line in acceptance_criteria if line.strip()]
    tasks_clean = [line.strip() for line in tasks if line.strip()]

    if not ac_clean:
        print("[Spec Manager] ERROR: Acceptance criteria cannot be empty.")
        sys.exit(1)
    if not tasks_clean:
        print("[Spec Manager] ERROR: Tasks cannot be empty.")
        sys.exit(1)

    now = now_iso()
    content_hash = compute_hash(spec_id, ac_clean, tasks_clean)

    spec_data = {
        "spec_id": spec_id,
        "title": title,
        "project_id": project_id,
        "team_id": team_id,
        "assigned_agent": agent_id,
        "status": "draft",
        "content_hash": content_hash,
        "acceptance_criteria": ac_clean,
        "tasks": tasks_clean,
        "dev_notes": "",
        "created_at": now,
        "created_by": "veda",
        "last_modified": now,
        "modified_by": "veda"
    }

    save_spec(spec_id, spec_data)

    # Register spec in project registry
    proj_reg = load_project_registry()
    if project_id in proj_reg.get("projects", {}):
        specs = proj_reg["projects"][project_id].get("specs", [])
        if spec_id not in specs:
            specs.append(spec_id)
            proj_reg["projects"][project_id]["specs"] = specs
            proj_reg["last_modified"] = now
            proj_reg["modified_by"] = "veda"
            save_project_registry(proj_reg)

    print(f"[Spec Manager] SUCCESS: Spec '{spec_id}' created.")
    print(f"[Spec Manager] Title: {title}")
    print(f"[Spec Manager] Project: {project_id} | Team: {team_id} | Agent: {agent_id}")
    print(f"[Spec Manager] Hash: {content_hash}")
    print(f"[Spec Manager] AC count: {len(ac_clean)} | Task count: {len(tasks_clean)}")
    print(f"[Spec Manager] Status: draft")
    print(f"[Spec Manager] Path: {spec_path(spec_id)}")


def verify(spec_id: str) -> None:
    spec = load_spec(spec_id)
    if not spec:
        print(f"[Spec Manager] ERROR: Spec '{spec_id}' not found.")
        sys.exit(1)

    stored_hash = spec.get("content_hash", "")
    ac = spec.get("acceptance_criteria", [])
    tasks = spec.get("tasks", [])
    computed_hash = compute_hash(spec_id, ac, tasks)

    if stored_hash != computed_hash:
        print(f"[Spec Manager] INTEGRITY FAILURE: Spec '{spec_id}' hash mismatch.")
        print(f"[Spec Manager] Stored:   {stored_hash}")
        print(f"[Spec Manager] Computed: {computed_hash}")
        print(f"[Spec Manager] Spec has been tampered with. Dispatch is BLOCKED.")
        sys.exit(1)

    print(f"[Spec Manager] INTEGRITY OK: Spec '{spec_id}' hash verified.")
    print(f"[Spec Manager] Hash: {stored_hash}")
    print(f"[Spec Manager] Spec is safe to dispatch.")


def update_status(spec_id: str, status: str) -> None:
    if status not in VALID_STATUSES:
        print(f"[Spec Manager] ERROR: Invalid status '{status}'.")
        print(f"[Spec Manager] Valid statuses: {sorted(VALID_STATUSES)}")
        sys.exit(1)

    spec = load_spec(spec_id)
    if not spec:
        print(f"[Spec Manager] ERROR: Spec '{spec_id}' not found.")
        sys.exit(1)

    now = now_iso()
    spec["status"] = status
    spec["last_modified"] = now
    spec["modified_by"] = "veda"
    save_spec(spec_id, spec)

    print(f"[Spec Manager] SUCCESS: Spec '{spec_id}' status updated to '{status}'.")


def list_specs(project_id: str) -> None:
    if not os.path.exists(SPECS_DIR):
        print(f"[Spec Manager] No specs found for project '{project_id}'.")
        return

    spec_files = [f for f in os.listdir(SPECS_DIR) if f.endswith(".spec.json")]
    project_specs = []

    for fname in sorted(spec_files):
        path = os.path.join(SPECS_DIR, fname)
        try:
            with open(path) as f:
                spec = json.load(f)
            if spec.get("project_id") == project_id:
                project_specs.append(spec)
        except (json.JSONDecodeError, OSError):
            pass

    if not project_specs:
        print(f"[Spec Manager] No specs found for project '{project_id}'.")
        return

    print(f"[Spec Manager] Specs for project '{project_id}' ({len(project_specs)} total):")
    for spec in project_specs:
        print(f"  {spec['spec_id']} [{spec['status']}] — agent={spec['assigned_agent']}")
        print(f"    Title: {spec['title']}")
        print(f"    AC: {len(spec['acceptance_criteria'])} | Tasks: {len(spec['tasks'])}")


def show(spec_id: str) -> None:
    spec = load_spec(spec_id)
    if not spec:
        print(f"[Spec Manager] ERROR: Spec '{spec_id}' not found.")
        sys.exit(1)

    print(f"[Spec Manager] Spec: {spec_id}")
    print(f"  Title:    {spec['title']}")
    print(f"  Status:   {spec['status']}")
    print(f"  Project:  {spec['project_id']}")
    print(f"  Team:     {spec['team_id']}")
    print(f"  Agent:    {spec['assigned_agent']}")
    print(f"  Hash:     {spec['content_hash']}")
    print(f"  Created:  {spec['created_at']}")
    print(f"  Acceptance Criteria:")
    for i, ac in enumerate(spec['acceptance_criteria'], 1):
        print(f"    AC #{i}: {ac}")
    print(f"  Tasks:")
    for i, task in enumerate(spec['tasks'], 1):
        print(f"    Task {i}: {task}")


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Ardha Factory Spec Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_create = subparsers.add_parser("create")
    p_create.add_argument("--spec-id", required=True)
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--project-id", required=True)
    p_create.add_argument("--team-id", required=True)
    p_create.add_argument("--agent-id", required=True)
    p_create.add_argument("--acceptance-criteria", required=True,
                          help="Pipe-separated AC lines")
    p_create.add_argument("--tasks", required=True,
                          help="Pipe-separated task lines")

    p_verify = subparsers.add_parser("verify")
    p_verify.add_argument("--spec-id", required=True)

    p_status = subparsers.add_parser("update-status")
    p_status.add_argument("--spec-id", required=True)
    p_status.add_argument("--status", required=True)

    p_list = subparsers.add_parser("list")
    p_list.add_argument("--project-id", required=True)

    p_show = subparsers.add_parser("show")
    p_show.add_argument("--spec-id", required=True)

    args = parser.parse_args()

    if args.command == "create":
        ac = [line.strip() for line in args.acceptance_criteria.split("|")]
        tasks = [line.strip() for line in args.tasks.split("|")]
        create(args.spec_id, args.title, args.project_id, args.team_id,
               args.agent_id, ac, tasks)
    elif args.command == "verify":
        verify(args.spec_id)
    elif args.command == "update-status":
        update_status(args.spec_id, args.status)
    elif args.command == "list":
        list_specs(args.project_id)
    elif args.command == "show":
        show(args.spec_id)


if __name__ == "__main__":
    main()
