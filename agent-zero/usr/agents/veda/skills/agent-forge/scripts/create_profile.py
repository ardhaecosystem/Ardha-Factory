#!/usr/bin/env python3
"""
Agent Forge — create_profile.py
Creates a new permanent agent profile directory for the Ardha Factory.
Called by Veda via the agent-forge skill after papa's approval.
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


AGENTS_DIR = "/a0/usr/agents"
VEDA_STATE_DIR = "/a0/usr/veda-state"
AGENT_REGISTRY_FILE = os.path.join(VEDA_STATE_DIR, "agent_registry.json")
RESTART_REQUIRED_FILE = os.path.join(VEDA_STATE_DIR, "restart_required.json")
FAISS_NAMESPACE_FILE = os.path.join(VEDA_STATE_DIR, "faiss_namespace_map.json")

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,30}$")


def validate_name(name: str) -> None:
    if not NAME_PATTERN.match(name):
        print(f"ERROR: Agent name '{name}' is invalid.")
        print("Names must match: ^[a-z][a-z0-9-]{2,30}$")
        print("Examples: frontend-dev, api-architect, qa-engineer")
        sys.exit(1)


def check_not_exists(name: str) -> None:
    profile_path = os.path.join(AGENTS_DIR, name)
    if os.path.exists(profile_path):
        print(f"ERROR: Agent profile '{name}' already exists at {profile_path}")
        print("Cannot overwrite an existing profile. Choose a different name.")
        sys.exit(1)


def create_profile_directory(name: str, role: str, team: str) -> str:
    profile_path = os.path.join(AGENTS_DIR, name)
    prompts_path = os.path.join(profile_path, "prompts")

    os.makedirs(prompts_path, exist_ok=True)

    # --- agent.json ---
    agent_json = {
        "title": name,
        "description": role,
        "context": (
            f"You are {name}, a specialised agent of the Ardha Factory. "
            f"Your role: {role}. "
            f"Operate strictly within your assigned memory namespace. "
            f"Never access resources outside your team scope. "
            f"Report all results in structured format to your orchestrator."
        )
    }
    with open(os.path.join(profile_path, "agent.json"), "w") as f:
        json.dump(agent_json, f, indent=2)

    # --- settings.json (minimal — inherits global defaults) ---
    settings_json = {
        "_comment": f"Profile settings for {name}. Add model overrides here if needed.",
        "_forged_at": datetime.now(timezone.utc).isoformat(),
        "_forged_by": "veda",
        "_team": team
    }
    with open(os.path.join(profile_path, "settings.json"), "w") as f:
        json.dump(settings_json, f, indent=2)

    # --- agents.json (no subordinates by default) ---
    agents_json = {}
    with open(os.path.join(profile_path, "agents.json"), "w") as f:
        json.dump(agents_json, f, indent=2)

    # --- agent.system.main.role.md ---
    team_line = (
        f"You are assigned to team: `{team}`."
        if team != "standalone"
        else "You are currently standalone — not assigned to any team."
    )
    role_md = f"""## Your role
{role}

## Your identity
You are `{name}`, a specialised sub-agent of the Ardha Factory.
{team_line}
Operate strictly within your assigned memory namespace.
Never access memory, knowledge, or project resources outside your team scope.
Always respond in structured format. Your orchestrator is Veda.
Report results clearly. Flag blockers immediately. Never proceed past a failed step silently.

## Your constraints
- You do not create other agents
- You do not modify registry files
- You do not access other teams' namespaces
- You escalate unresolvable issues to Veda immediately
- You complete your assigned Spec task and report back
"""
    with open(os.path.join(prompts_path, "agent.system.main.role.md"), "w") as f:
        f.write(role_md)

    return profile_path


def update_agent_registry(name: str, role: str, team: str, profile_path: str) -> None:
    now = datetime.now(timezone.utc).isoformat()

    # Load or initialise registry
    if os.path.exists(AGENT_REGISTRY_FILE):
        with open(AGENT_REGISTRY_FILE, "r") as f:
            registry = json.load(f)
    else:
        registry = {
            "schema_version": "3.0.0",
            "type": "agent_registry",
            "agents": {},
            "last_modified": None,
            "modified_by": None
        }

    registry["agents"][name] = {
        "agent_id": name,
        "profile": name,
        "role": role,
        "team_id": team if team != "standalone" else None,
        "status": "standalone" if team == "standalone" else "assigned",
        "created_at": now,
        "created_by": "veda",
        "profile_path": profile_path,
        "model_overrides": {},
        "tools_enabled": [],
        "mcp_servers": []
    }
    registry["last_modified"] = now
    registry["modified_by"] = "veda"

    save_registry(AGENT_REGISTRY_FILE, registry)


def set_restart_required(name: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "3.0.0",
        "type": "restart_required",
        "required": True,
        "reason": f"New agent profile '{name}' forged — extensions must reload",
        "triggered_by": "veda",
        "triggered_at": now,
        "pending_changes": [
            f"agents/{name}/ directory created"
        ]
    }
    save_registry(RESTART_REQUIRED_FILE, payload)


def main():
    parser = argparse.ArgumentParser(description="Forge a new Ardha Factory agent profile.")
    parser.add_argument("--name", required=True, help="Agent name (lowercase, hyphens)")
    parser.add_argument("--role", required=True, help="Agent role description")
    parser.add_argument("--team", required=True, help="Team ID or 'standalone'")
    args = parser.parse_args()

    name = args.name.strip()
    role = args.role.strip()
    team = args.team.strip()

    print(f"[Agent Forge] Forging agent: '{name}'")
    print(f"[Agent Forge] Role: {role}")
    print(f"[Agent Forge] Team: {team}")

    # Validations
    validate_name(name)
    check_not_exists(name)

    # Create profile
    profile_path = create_profile_directory(name, role, team)
    print(f"[Agent Forge] Profile created at: {profile_path}")

    # Update agent registry
    update_agent_registry(name, role, team, profile_path)
    print(f"[Agent Forge] Agent registry updated.")

    # Set restart required
    set_restart_required(name)
    print(f"[Agent Forge] restart_required.json set to true.")

    print(f"[Agent Forge] SUCCESS: Agent '{name}' forged.")
    print(f"[Agent Forge] IMPORTANT: Papa must restart the container before '{name}' can be used.")


if __name__ == "__main__":
    main()
