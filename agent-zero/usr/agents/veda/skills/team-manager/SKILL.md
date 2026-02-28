---
name: "team-manager"
description: "Creates, updates, and dissolves Teams in the Ardha Factory. Assigns and unassigns agents to teams. Updates team registry and FAISS namespace map. Use when papa approves team operations."
version: "1.0.0"
author: "Ardha Factory"
tags: ["ardha", "orchestration", "team-manager", "registry", "meta-orchestrator"]
trigger_patterns:
  - "create team"
  - "new team"
  - "dissolve team"
  - "assign agent to team"
  - "unassign agent"
  - "team manager"
  - "manage team"
---

# Team Manager

Creates, updates, and dissolves Teams in the Ardha Factory.
Only Veda may invoke this skill. Always obtain papa's explicit approval before any team operation.

## When to Use

Use this skill when:
- Papa has approved creation of a new Team
- Papa has approved dissolving an existing Team
- Papa has approved assigning a standalone agent to a Team
- Papa has approved unassigning an agent from a Team

Never mutate team state without papa's explicit approval.

## Operations

### Create a Team

```bash
python3 /a0/usr/agents/veda/skills/team-manager/scripts/team_ops.py \
  create-team \
  --team-id "TEAM_ID" \
  --purpose "TEAM_PURPOSE"
```

Team ID must match: `^team-[a-z][a-z0-9-]{1,25}$`
Examples: `team-frontend`, `team-backend`, `team-qa`

### Assign Agent to Team

Agent must already exist in agent_registry.json (forged via agent-forge skill).

```bash
python3 /a0/usr/agents/veda/skills/team-manager/scripts/team_ops.py \
  assign-agent \
  --team-id "TEAM_ID" \
  --agent-id "AGENT_ID"
```

### Unassign Agent from Team

Moves agent back to standalone status. Does not delete the agent profile.

```bash
python3 /a0/usr/agents/veda/skills/team-manager/scripts/team_ops.py \
  unassign-agent \
  --team-id "TEAM_ID" \
  --agent-id "AGENT_ID"
```

### Dissolve a Team

Team must have no active Specs before dissolution. All agents are moved to standalone.

```bash
python3 /a0/usr/agents/veda/skills/team-manager/scripts/team_ops.py \
  dissolve-team \
  --team-id "TEAM_ID"
```

### List Teams

```bash
python3 /a0/usr/agents/veda/skills/team-manager/scripts/team_ops.py \
  list-teams
```

## Post-Operation Reporting

After every team operation, report to papa:
- Operation performed
- Team ID affected
- Agents affected (if any)
- Current team state (agent count, project count)
- Any warnings

## Important Constraints

- Never create a team without papa's approval
- Never dissolve a team that has active Specs in pipeline_state.json
- Never assign an agent that does not exist in agent_registry.json
- Team memory namespace is automatically assigned as the team ID
- FAISS namespace map is updated on every team creation
