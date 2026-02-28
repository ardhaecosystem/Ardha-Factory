---
name: "agent-forge"
description: "Creates new permanent agent profiles for the Ardha Factory. Use when papa approves creation of a new agent. Writes the agent profile directory structure, registers the agent in veda-state, and sets the restart_required flag."
version: "1.0.0"
author: "Ardha Factory"
tags: ["ardha", "orchestration", "agent-forge", "profile", "meta-orchestrator"]
trigger_patterns:
  - "forge agent"
  - "create agent"
  - "new agent profile"
  - "agent forge"
  - "create new agent"
---

# Agent Forge

Creates a new permanent agent profile for the Ardha Factory.
Only Veda may invoke this skill. Always obtain papa's explicit approval before forging.

## When to Use

Use this skill when:
- Papa has explicitly approved creation of a new agent
- A new capability is needed that no existing agent covers
- A team requires a new specialist role

Never use this skill speculatively or without papa's approval.

## Pre-Forge Checklist

Before invoking, confirm all of the following with papa:

- [ ] Agent name agreed (lowercase, hyphens only, 3-30 chars)
- [ ] Agent role and purpose clearly defined
- [ ] Target team confirmed (or standalone confirmed)
- [ ] Model overrides required? (or inherits global defaults)
- [ ] Tools required beyond defaults?

## Forge Process

### Step 1: Validate the agent name

Agent names must match: `^[a-z][a-z0-9-]{2,30}$`

Valid examples: `frontend-dev`, `api-architect`, `qa-engineer`
Invalid examples: `Frontend Dev`, `agent_1`, `a`

### Step 2: Run the creation script

```bash
python3 /a0/usr/agents/veda/skills/agent-forge/scripts/create_profile.py \
  --name "AGENT_NAME" \
  --role "AGENT_ROLE_DESCRIPTION" \
  --team "TEAM_ID_OR_standalone"
```

### Step 3: Run the validation script

```bash
python3 /a0/usr/agents/veda/skills/agent-forge/scripts/validate_profile.py \
  --name "AGENT_NAME"
```

Validation must pass before reporting to papa. If validation fails, report the error to papa and do not proceed.

### Step 4: Report to papa

After successful validation, report:
- Agent name and profile path created
- Role assigned
- Team assignment (or standalone status)
- Restart required — instruct papa to restart the container before this agent can be used
- Any warnings from validation

## Output Structure

The forge creates this directory structure:

```
/a0/usr/agents/{name}/
├── agent.json              — profile metadata
├── settings.json           — model/memory overrides (minimal)
├── prompts/
│   └── agent.system.main.role.md   — agent role definition
└── agents.json             — subordinate agent config (empty by default)
```

## Post-Forge State

After a successful forge:
- Agent profile directory exists at `/a0/usr/agents/{name}/`
- `restart_required.json` is set to `true`
- Agent registry entry is written to `usr/veda-state/agent_registry.json`
- Container must be restarted before the agent can be used via `call_subordinate`

## Important Constraints

- Never forge an agent with the same name as an existing profile
- Never forge without papa's approval
- Always set restart_required after forging
- The forged agent is standalone until explicitly assigned to a team
- Model defaults inherit from global `settings.json` unless overridden
