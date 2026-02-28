---
name: "project-forge"
description: "Creates and manages Agent-Zero projects for the Ardha Factory. Binds projects to teams. Updates project registry. Use when papa approves project creation or management operations."
version: "1.0.0"
author: "Ardha Factory"
tags: ["ardha", "orchestration", "project-forge", "registry", "meta-orchestrator"]
trigger_patterns:
  - "create project"
  - "new project"
  - "forge project"
  - "project forge"
  - "bind project"
  - "link project to team"
  - "archive project"
---

# Project Forge

Creates and manages Agent-Zero projects for the Ardha Factory.
Only Veda may invoke this skill. Always obtain papa's explicit approval before any project operation.

## When to Use

Use this skill when:
- Papa has approved creation of a new Project
- Papa has approved binding an existing project to a team
- Papa has approved archiving a completed project

Never create or modify projects without papa's explicit approval.

## Pre-Forge Checklist

Before invoking, confirm all of the following with papa:

- [ ] Project name agreed (lowercase, hyphens only, must start with proj-)
- [ ] Project title and description defined
- [ ] Target team confirmed and exists in team_registry.json
- [ ] Memory mode confirmed (always "own" for isolation)

## Operations

### Create a Project

```bash
python3 /a0/usr/agents/veda/skills/project-forge/scripts/project_ops.py \
  create-project \
  --project-id "proj-NAME" \
  --title "PROJECT TITLE" \
  --description "PROJECT DESCRIPTION" \
  --team-id "TEAM_ID"
```

Project ID must match: `^proj-[a-z][a-z0-9-]{1,25}$`
Examples: `proj-dashboard`, `proj-api-gateway`, `proj-mobile-app`

### List Projects

```bash
python3 /a0/usr/agents/veda/skills/project-forge/scripts/project_ops.py \
  list-projects
```

### Archive a Project

Marks project as archived in registry. Does not delete project files.

```bash
python3 /a0/usr/agents/veda/skills/project-forge/scripts/project_ops.py \
  archive-project \
  --project-id "proj-NAME"
```

## Project Structure Created

```
usr/projects/{project-id}/
├── .a0proj/
│   ├── project.json          — Agent-Zero native project metadata
│   ├── instructions/         — Project instruction files
│   └── knowledge/            — Project knowledge base
│       ├── main/
│       ├── fragments/
│       ├── solutions/
│       └── skills/
```

## Post-Forge Reporting

After every project operation, report to papa:
- Operation performed
- Project ID and path created
- Team bound to project
- Memory mode (always "own")
- Any warnings

## Important Constraints

- Never create a project without papa's approval
- Always use memory mode "own" — never "global"
- Project ID must start with "proj-"
- Team must exist in team_registry.json before binding
- Never archive a project with active Specs in pipeline_state.json
