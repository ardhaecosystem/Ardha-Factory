#!/usr/bin/env python3
"""
Team Manager — team_ops.py
CRUD operations for Ardha Factory Teams.
Called by Veda via the team-manager skill after papa's approval.
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

VEDA_STATE_DIR = "/a0/usr/veda-state"
TEAM_REGISTRY_FILE = os.path.join(VEDA_STATE_DIR, "team_registry.json")
AGENT_REGISTRY_FILE = os.path.join(VEDA_STATE_DIR, "agent_registry.json")
PROJECT_REGISTRY_FILE = os.path.join(VEDA_STATE_DIR, "project_registry.json")
PIPELINE_STATE_FILE = os.path.join(VEDA_STATE_DIR, "pipeline_state.json")
FAISS_NAMESPACE_FILE = os.path.join(VEDA_STATE_DIR, "faiss_namespace_map.json")

TEAM_ID_PATTERN = re.compile(r"^team-[a-z][a-z0-9-]{1,25}$")


# --- Helpers ---

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)



def load_team_registry() -> dict:
    data = load_json(TEAM_REGISTRY_FILE)
    if not data:
        return {
            "schema_version": "3.0.0",
            "type": "team_registry",
            "teams": {},
            "last_modified": None,
            "modified_by": None
        }
    return data


def load_agent_registry() -> dict:
    data = load_json(AGENT_REGISTRY_FILE)
    if not data:
        return {"schema_version": "3.0.0", "type": "agent_registry", "agents": {}}
    return data


def load_faiss_map() -> dict:
    data = load_json(FAISS_NAMESPACE_FILE)
    if not data:
        return {
            "schema_version": "3.0.0",
            "type": "faiss_namespace_map",
            "namespaces": {},
            "rules": {
                "cross_namespace_access": "forbidden",
                "default_isolation_level": "strict"
            }
        }
    return data


def get_active_specs_for_team(team_id: str) -> list:
    """Check pipeline_state for any active or queued specs assigned to this team."""
    pipeline = load_json(PIPELINE_STATE_FILE)
    if not pipeline:
        return []
    assignments = pipeline.get("team_assignments", {})
    active_specs = []
    current = pipeline.get("current_spec")
    queue = pipeline.get("queue", [])
    all_active = ([current] if current and current != "none" else []) + queue
    for spec_id in all_active:
        if assignments.get(spec_id) == team_id:
            active_specs.append(spec_id)
    return active_specs


# --- Operations ---

def create_team(team_id: str, purpose: str) -> None:
    if not TEAM_ID_PATTERN.match(team_id):
        print(f"ERROR: Team ID '{team_id}' is invalid.")
        print("Team IDs must match: ^team-[a-z][a-z0-9-]{1,25}$")
        print("Examples: team-frontend, team-backend, team-qa")
        sys.exit(1)

    registry = load_team_registry()
    if team_id in registry["teams"]:
        print(f"ERROR: Team '{team_id}' already exists.")
        sys.exit(1)

    now = now_iso()
    registry["teams"][team_id] = {
        "team_id": team_id,
        "created_at": now,
        "created_by": "veda",
        "status": "active",
        "purpose": purpose,
        "agents": [],
        "projects": [],
        "memory_subdir": team_id,
        "isolation_level": "strict"
    }
    registry["last_modified"] = now
    registry["modified_by"] = "veda"
    save_registry(TEAM_REGISTRY_FILE, registry)

    # Register FAISS namespace for this team
    faiss = load_faiss_map()
    faiss["namespaces"][team_id] = {
        "owner": team_id,
        "owner_type": "team",
        "purpose": f"Memory namespace for {team_id}",
        "created_at": now,
        "status": "active",
        "isolation_level": "strict"
    }
    faiss["last_modified"] = now
    faiss["modified_by"] = "veda"
    save_registry(FAISS_NAMESPACE_FILE, faiss)

    print(f"[Team Manager] SUCCESS: Team '{team_id}' created.")
    print(f"[Team Manager] Purpose: {purpose}")
    print(f"[Team Manager] Memory namespace: {team_id}")
    print(f"[Team Manager] FAISS namespace registered.")


def assign_agent(team_id: str, agent_id: str) -> None:
    registry = load_team_registry()
    if team_id not in registry["teams"]:
        print(f"ERROR: Team '{team_id}' does not exist.")
        sys.exit(1)
    if registry["teams"][team_id]["status"] != "active":
        print(f"ERROR: Team '{team_id}' is not active.")
        sys.exit(1)

    agent_reg = load_agent_registry()
    if agent_id not in agent_reg.get("agents", {}):
        print(f"ERROR: Agent '{agent_id}' not found in agent_registry.json.")
        print("Forge the agent first using the agent-forge skill.")
        sys.exit(1)

    if agent_id in registry["teams"][team_id]["agents"]:
        print(f"WARN: Agent '{agent_id}' is already assigned to team '{team_id}'.")
        sys.exit(0)

    now = now_iso()

    # Update team registry
    registry["teams"][team_id]["agents"].append(agent_id)
    registry["last_modified"] = now
    registry["modified_by"] = "veda"
    save_registry(TEAM_REGISTRY_FILE, registry)

    # Update agent registry
    agent_reg["agents"][agent_id]["team_id"] = team_id
    agent_reg["agents"][agent_id]["status"] = "assigned"
    agent_reg["last_modified"] = now
    agent_reg["modified_by"] = "veda"
    save_registry(AGENT_REGISTRY_FILE, agent_reg)

    print(f"[Team Manager] SUCCESS: Agent '{agent_id}' assigned to team '{team_id}'.")
    print(f"[Team Manager] Agent memory namespace: {team_id}")


def unassign_agent(team_id: str, agent_id: str) -> None:
    registry = load_team_registry()
    if team_id not in registry["teams"]:
        print(f"ERROR: Team '{team_id}' does not exist.")
        sys.exit(1)

    if agent_id not in registry["teams"][team_id]["agents"]:
        print(f"ERROR: Agent '{agent_id}' is not assigned to team '{team_id}'.")
        sys.exit(1)

    now = now_iso()

    # Update team registry
    registry["teams"][team_id]["agents"].remove(agent_id)
    registry["last_modified"] = now
    registry["modified_by"] = "veda"
    save_registry(TEAM_REGISTRY_FILE, registry)

    # Update agent registry
    agent_reg = load_agent_registry()
    if agent_id in agent_reg.get("agents", {}):
        agent_reg["agents"][agent_id]["team_id"] = None
        agent_reg["agents"][agent_id]["status"] = "standalone"
        agent_reg["last_modified"] = now
        agent_reg["modified_by"] = "veda"
        save_registry(AGENT_REGISTRY_FILE, agent_reg)

    print(f"[Team Manager] SUCCESS: Agent '{agent_id}' unassigned from team '{team_id}'.")
    print(f"[Team Manager] Agent status: standalone")


def dissolve_team(team_id: str) -> None:
    registry = load_team_registry()
    if team_id not in registry["teams"]:
        print(f"ERROR: Team '{team_id}' does not exist.")
        sys.exit(1)
    if registry["teams"][team_id]["status"] == "dissolved":
        print(f"ERROR: Team '{team_id}' is already dissolved.")
        sys.exit(1)

    # Block if active specs exist
    active_specs = get_active_specs_for_team(team_id)
    if active_specs:
        print(f"ERROR: Team '{team_id}' has active Specs: {active_specs}")
        print("Cannot dissolve a team with active or queued Specs.")
        print("Complete or cancel all Specs before dissolving.")
        sys.exit(1)

    now = now_iso()
    agents_in_team = registry["teams"][team_id]["agents"].copy()

    # Move all agents to standalone
    agent_reg = load_agent_registry()
    for agent_id in agents_in_team:
        if agent_id in agent_reg.get("agents", {}):
            agent_reg["agents"][agent_id]["team_id"] = None
            agent_reg["agents"][agent_id]["status"] = "standalone"
    if agents_in_team:
        agent_reg["last_modified"] = now
        agent_reg["modified_by"] = "veda"
        save_registry(AGENT_REGISTRY_FILE, agent_reg)

    # Mark team as dissolved
    registry["teams"][team_id]["status"] = "dissolved"
    registry["teams"][team_id]["dissolved_at"] = now
    registry["teams"][team_id]["agents"] = []
    registry["last_modified"] = now
    registry["modified_by"] = "veda"
    save_registry(TEAM_REGISTRY_FILE, registry)

    # Mark FAISS namespace as dissolved
    faiss = load_faiss_map()
    if team_id in faiss.get("namespaces", {}):
        faiss["namespaces"][team_id]["status"] = "dissolved"
        faiss["namespaces"][team_id]["dissolved_at"] = now
        faiss["last_modified"] = now
        faiss["modified_by"] = "veda"
        save_registry(FAISS_NAMESPACE_FILE, faiss)

    print(f"[Team Manager] SUCCESS: Team '{team_id}' dissolved.")
    print(f"[Team Manager] Agents moved to standalone: {agents_in_team}")
    print(f"[Team Manager] FAISS namespace '{team_id}' marked as dissolved.")
    print(f"[Team Manager] Note: FAISS memory data is preserved for audit purposes.")


def list_teams() -> None:
    registry = load_team_registry()
    teams = registry.get("teams", {})
    if not teams:
        print("[Team Manager] No teams registered yet.")
        return
    print(f"[Team Manager] Teams ({len(teams)} total):")
    for tid, t in teams.items():
        status = t.get("status", "unknown")
        agents = t.get("agents", [])
        projects = t.get("projects", [])
        purpose = t.get("purpose", "")
        print(f"  {tid} [{status}] — {len(agents)} agent(s), {len(projects)} project(s)")
        print(f"    Purpose: {purpose}")
        if agents:
            print(f"    Agents: {agents}")


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Ardha Factory Team Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-team
    p_create = subparsers.add_parser("create-team")
    p_create.add_argument("--team-id", required=True)
    p_create.add_argument("--purpose", required=True)

    # assign-agent
    p_assign = subparsers.add_parser("assign-agent")
    p_assign.add_argument("--team-id", required=True)
    p_assign.add_argument("--agent-id", required=True)

    # unassign-agent
    p_unassign = subparsers.add_parser("unassign-agent")
    p_unassign.add_argument("--team-id", required=True)
    p_unassign.add_argument("--agent-id", required=True)

    # dissolve-team
    p_dissolve = subparsers.add_parser("dissolve-team")
    p_dissolve.add_argument("--team-id", required=True)

    # list-teams
    subparsers.add_parser("list-teams")

    args = parser.parse_args()

    if args.command == "create-team":
        create_team(args.team_id, args.purpose)
    elif args.command == "assign-agent":
        assign_agent(args.team_id, args.agent_id)
    elif args.command == "unassign-agent":
        unassign_agent(args.team_id, args.agent_id)
    elif args.command == "dissolve-team":
        dissolve_team(args.team_id)
    elif args.command == "list-teams":
        list_teams()


if __name__ == "__main__":
    main()
