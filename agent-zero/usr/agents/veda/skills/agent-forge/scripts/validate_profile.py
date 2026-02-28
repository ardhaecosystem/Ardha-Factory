#!/usr/bin/env python3
"""
Agent Forge — validate_profile.py
Validates a forged agent profile is complete and correctly structured.
Called by Veda after create_profile.py to confirm the profile is ready.
"""

import argparse
import json
import os
import re
import sys

AGENTS_DIR = "/a0/usr/agents"
VEDA_STATE_DIR = "/a0/usr/veda-state"
AGENT_REGISTRY_FILE = os.path.join(VEDA_STATE_DIR, "agent_registry.json")

REQUIRED_FILES = [
    "agent.json",
    "settings.json",
    "agents.json",
    "prompts/agent.system.main.role.md",
]

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,30}$")


def validate_profile(name: str) -> tuple[bool, list[str], list[str]]:
    errors = []
    warnings = []
    profile_path = os.path.join(AGENTS_DIR, name)

    # --- Name format ---
    if not NAME_PATTERN.match(name):
        errors.append(f"Agent name '{name}' does not match required pattern.")

    # --- Profile directory exists ---
    if not os.path.isdir(profile_path):
        errors.append(f"Profile directory does not exist: {profile_path}")
        return False, errors, warnings

    # --- Required files ---
    for rel_path in REQUIRED_FILES:
        full_path = os.path.join(profile_path, rel_path)
        if not os.path.isfile(full_path):
            errors.append(f"Missing required file: {rel_path}")
        else:
            # Check not empty
            if os.path.getsize(full_path) == 0:
                errors.append(f"File is empty: {rel_path}")

    # --- Validate agent.json structure ---
    agent_json_path = os.path.join(profile_path, "agent.json")
    if os.path.isfile(agent_json_path):
        try:
            with open(agent_json_path) as f:
                data = json.load(f)
            for field in ["title", "description", "context"]:
                if not data.get(field):
                    errors.append(f"agent.json missing or empty field: '{field}'")
        except json.JSONDecodeError as e:
            errors.append(f"agent.json is not valid JSON: {e}")

    # --- Validate settings.json ---
    settings_path = os.path.join(profile_path, "settings.json")
    if os.path.isfile(settings_path):
        try:
            with open(settings_path) as f:
                json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"settings.json is not valid JSON: {e}")

    # --- Validate agents.json ---
    agents_path = os.path.join(profile_path, "agents.json")
    if os.path.isfile(agents_path):
        try:
            with open(agents_path) as f:
                json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"agents.json is not valid JSON: {e}")

    # --- Validate role prompt has content ---
    role_path = os.path.join(profile_path, "prompts/agent.system.main.role.md")
    if os.path.isfile(role_path):
        with open(role_path) as f:
            content = f.read().strip()
        if len(content) < 50:
            warnings.append("Role prompt is very short — consider expanding it.")
        if name not in content:
            warnings.append(f"Agent name '{name}' not found in role prompt.")

    # --- Check agent registry entry ---
    if os.path.isfile(AGENT_REGISTRY_FILE):
        try:
            with open(AGENT_REGISTRY_FILE) as f:
                registry = json.load(f)
            if name not in registry.get("agents", {}):
                errors.append(f"Agent '{name}' not found in agent_registry.json.")
        except json.JSONDecodeError as e:
            warnings.append(f"Could not parse agent_registry.json: {e}")
    else:
        warnings.append("agent_registry.json does not exist yet.")

    passed = len(errors) == 0
    return passed, errors, warnings


def main():
    parser = argparse.ArgumentParser(description="Validate an Ardha Factory agent profile.")
    parser.add_argument("--name", required=True, help="Agent name to validate")
    args = parser.parse_args()

    name = args.name.strip()
    print(f"[Agent Forge Validator] Validating profile: '{name}'")

    passed, errors, warnings = validate_profile(name)

    if warnings:
        for w in warnings:
            print(f"  WARN: {w}")

    if errors:
        for e in errors:
            print(f"  ERROR: {e}")
        print(f"[Agent Forge Validator] FAILED — {len(errors)} error(s) found.")
        sys.exit(1)

    print(f"[Agent Forge Validator] PASSED — profile '{name}' is valid and ready.")
    print(f"[Agent Forge Validator] Path: /a0/usr/agents/{name}/")
    print(f"[Agent Forge Validator] Remember: papa must restart the container before this agent can be used.")


if __name__ == "__main__":
    main()
