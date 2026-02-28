#!/usr/bin/env python3
"""
Project Forge — project_ops.py
Creates and manages Agent-Zero projects for the Ardha Factory.
Called by Veda via the project-forge skill after papa's approval.

Uses Agent-Zero's native project structure directly — compatible with
the framework's project loading, activation, and memory isolation systems.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

# registry_io — checksum-protected registry I/O
import sys as _sys
if "/a0/usr/agents/veda/scripts" not in _sys.path:
    _sys.path.insert(0, "/a0/usr/agents/veda/scripts")
from registry_io import save_registry, CorruptionError

# Agent-Zero native paths
A0_ROOT = "/a0"
PROJECTS_DIR = os.path.join(A0_ROOT, "usr/projects")
PROJECT_META_DIR = ".a0proj"

# Veda state paths
VEDA_STATE_DIR = "/a0/usr/veda-state"
PROJECT_REGISTRY_FILE = os.path.join(VEDA_STATE_DIR, "project_registry.json")
TEAM_REGISTRY_FILE = os.path.join(VEDA_STATE_DIR, "team_registry.json")
PIPELINE_STATE_FILE = os.path.join(VEDA_STATE_DIR, "pipeline_state.json")

PROJECT_ID_PATTERN = re.compile(r"^proj-[a-z][a-z0-9-]{1,25}$")

# Memory area subdirs — must match Agent-Zero's Memory.Area enum values
MEMORY_AREAS = ["main", "fragments", "solutions", "skills"]


# --- Helpers ---

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)



def load_project_registry() -> dict:
    data = load_json(PROJECT_REGISTRY_FILE)
    if not data:
        return {
            "schema_version": "3.0.0",
            "type": "project_registry",
            "projects": {},
            "last_modified": None,
            "modified_by": None
        }
    return data


def load_team_registry() -> dict:
    return load_json(TEAM_REGISTRY_FILE)


def get_active_specs_for_project(project_id: str) -> list:
    """Check pipeline_state for any active or queued specs assigned to this project."""
    pipeline = load_json(PIPELINE_STATE_FILE)
    if not pipeline:
        return []
    current = pipeline.get("current_spec")
    queue = pipeline.get("queue", [])
    all_active = ([current] if current and current != "none" else []) + queue

    # Check project registry for this project's specs
    proj_reg = load_project_registry()
    project_specs = set(
        proj_reg.get("projects", {})
        .get(project_id, {})
        .get("specs", [])
    )
    return [s for s in all_active if s in project_specs]


def validate_team_exists(team_id: str) -> None:
    team_reg = load_team_registry()
    teams = team_reg.get("teams", {})
    if team_id not in teams:
        print(f"ERROR: Team '{team_id}' does not exist in team_registry.json.")
        print("Create the team first using the team-manager skill.")
        sys.exit(1)
    if teams[team_id].get("status") != "active":
        print(f"ERROR: Team '{team_id}' is not active (status: {teams[team_id].get('status')}).")
        sys.exit(1)


# --- Native A0 project structure builder ---

def _default_file_structure_settings() -> dict:
    """Matches Agent-Zero's _default_file_structure_settings() defaults."""
    return {
        "enabled": True,
        "max_depth": 3,
        "max_files": 20,
        "max_folders": 10,
        "max_lines": 50,
        "gitignore": ""
    }


def create_a0_project_structure(project_id: str, title: str, description: str) -> str:
    """
    Creates the native Agent-Zero project directory structure.
    Mirrors what Agent-Zero's create_project() + create_project_meta_folders() do.
    """
    project_path = os.path.join(PROJECTS_DIR, project_id)
    meta_path = os.path.join(project_path, PROJECT_META_DIR)
    instructions_path = os.path.join(meta_path, "instructions")
    knowledge_path = os.path.join(meta_path, "knowledge")

    # Create directory tree
    os.makedirs(instructions_path, exist_ok=True)
    for area in MEMORY_AREAS:
        os.makedirs(os.path.join(knowledge_path, area), exist_ok=True)

    # Write project.json — native Agent-Zero format
    project_json = {
        "title": title,
        "description": description,
        "instructions": "",
        "color": "",
        "git_url": "",
        "memory": "own",
        "file_structure": _default_file_structure_settings()
    }
    project_json_path = os.path.join(meta_path, "project.json")
    with open(project_json_path, "w") as f:
        json.dump(project_json, f, indent=2)

    return project_path


# --- Operations ---

def create_project(project_id: str, title: str, description: str, team_id: str) -> None:
    if not PROJECT_ID_PATTERN.match(project_id):
        print(f"ERROR: Project ID '{project_id}' is invalid.")
        print("Project IDs must match: ^proj-[a-z][a-z0-9-]{1,25}$")
        print("Examples: proj-dashboard, proj-api-gateway")
        sys.exit(1)

    # Check team exists
    validate_team_exists(team_id)

    # Check project doesn't already exist
    project_path = os.path.join(PROJECTS_DIR, project_id)
    if os.path.exists(project_path):
        print(f"ERROR: Project '{project_id}' already exists at {project_path}")
        sys.exit(1)

    # Check not already in registry
    proj_reg = load_project_registry()
    if project_id in proj_reg.get("projects", {}):
        print(f"ERROR: Project '{project_id}' already exists in project_registry.json.")
        sys.exit(1)

    now = now_iso()

    # Create native A0 project structure
    project_path = create_a0_project_structure(project_id, title, description)
    print(f"[Project Forge] A0 project structure created at: {project_path}")

    # Register in Veda project registry
    proj_reg["projects"][project_id] = {
        "project_id": project_id,
        "a0_project_name": project_id,
        "title": title,
        "description": description,
        "team_id": team_id,
        "status": "active",
        "memory_mode": "own",
        "specs": [],
        "created_at": now,
        "created_by": "veda"
    }
    proj_reg["last_modified"] = now
    proj_reg["modified_by"] = "veda"
    save_registry(PROJECT_REGISTRY_FILE, proj_reg)
    print(f"[Project Forge] Project registry updated.")

    # Update team registry — add project to team's project list
    team_reg = load_team_registry()
    if team_id in team_reg.get("teams", {}):
        if project_id not in team_reg["teams"][team_id]["projects"]:
            team_reg["teams"][team_id]["projects"].append(project_id)
            team_reg["last_modified"] = now
            team_reg["modified_by"] = "veda"
            save_registry(TEAM_REGISTRY_FILE, team_reg)
            print(f"[Project Forge] Team registry updated — project bound to '{team_id}'.")

    print(f"[Project Forge] SUCCESS: Project '{project_id}' created.")
    print(f"[Project Forge] Title: {title}")
    print(f"[Project Forge] Team: {team_id}")
    print(f"[Project Forge] Memory mode: own (isolated FAISS)")
    print(f"[Project Forge] Path: {project_path}")


def archive_project(project_id: str) -> None:
    proj_reg = load_project_registry()
    if project_id not in proj_reg.get("projects", {}):
        print(f"ERROR: Project '{project_id}' not found in project_registry.json.")
        sys.exit(1)

    if proj_reg["projects"][project_id].get("status") == "archived":
        print(f"ERROR: Project '{project_id}' is already archived.")
        sys.exit(1)

    # Block if active specs exist
    active_specs = get_active_specs_for_project(project_id)
    if active_specs:
        print(f"ERROR: Project '{project_id}' has active Specs: {active_specs}")
        print("Complete or cancel all Specs before archiving.")
        sys.exit(1)

    now = now_iso()
    team_id = proj_reg["projects"][project_id].get("team_id")

    # Mark archived in project registry
    proj_reg["projects"][project_id]["status"] = "archived"
    proj_reg["projects"][project_id]["archived_at"] = now
    proj_reg["last_modified"] = now
    proj_reg["modified_by"] = "veda"
    save_registry(PROJECT_REGISTRY_FILE, proj_reg)

    # Remove from team's project list
    if team_id:
        team_reg = load_team_registry()
        if team_id in team_reg.get("teams", {}):
            projects = team_reg["teams"][team_id].get("projects", [])
            if project_id in projects:
                projects.remove(project_id)
                team_reg["teams"][team_id]["projects"] = projects
                team_reg["last_modified"] = now
                team_reg["modified_by"] = "veda"
                save_registry(TEAM_REGISTRY_FILE, team_reg)

    print(f"[Project Forge] SUCCESS: Project '{project_id}' archived.")
    print(f"[Project Forge] Project files preserved at: {os.path.join(PROJECTS_DIR, project_id)}")
    print(f"[Project Forge] Project removed from team '{team_id}' active list.")


def list_projects() -> None:
    proj_reg = load_project_registry()
    projects = proj_reg.get("projects", {})
    if not projects:
        print("[Project Forge] No projects registered yet.")
        return
    print(f"[Project Forge] Projects ({len(projects)} total):")
    for pid, p in projects.items():
        status = p.get("status", "unknown")
        team = p.get("team_id", "unbound")
        spec_count = len(p.get("specs", []))
        title = p.get("title", "")
        print(f"  {pid} [{status}] — team={team}, {spec_count} spec(s)")
        print(f"    Title: {title}")


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Ardha Factory Project Forge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-project
    p_create = subparsers.add_parser("create-project")
    p_create.add_argument("--project-id", required=True)
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--description", required=True)
    p_create.add_argument("--team-id", required=True)

    # archive-project
    p_archive = subparsers.add_parser("archive-project")
    p_archive.add_argument("--project-id", required=True)

    # list-projects
    subparsers.add_parser("list-projects")

    args = parser.parse_args()

    if args.command == "create-project":
        create_project(args.project_id, args.title, args.description, args.team_id)
    elif args.command == "archive-project":
        archive_project(args.project_id)
    elif args.command == "list-projects":
        list_projects()


if __name__ == "__main__":
    main()
