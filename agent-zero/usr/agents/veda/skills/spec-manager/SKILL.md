---
name: "spec-manager"
description: "Creates, hashes, verifies, and manages Specs for the Ardha Factory. Computes SHA-256 content hashes for immutability. Use when papa approves a new Spec or before dispatching an existing Spec."
version: "1.0.0"
author: "Ardha Factory"
tags: ["ardha", "orchestration", "spec-manager", "hash", "immutability"]
trigger_patterns:
  - "create spec"
  - "new spec"
  - "verify spec"
  - "spec hash"
  - "spec manager"
  - "check spec integrity"
---

# Spec Manager

Creates and manages Specs for the Ardha Factory with SHA-256 content hash immutability.
Only Veda may invoke this skill. Always obtain papa's explicit approval before creating a Spec.

## When to Use

- **When papa approves a new Spec** — create and hash it
- **Before dispatching any Spec** — verify hash integrity
- **When listing project Specs** — list with status

## Spec ID Format

`SPEC-{team-id}-{project-id}-{NNN}`

Examples:
- `SPEC-team-frontend-proj-dashboard-001`
- `SPEC-team-backend-proj-api-001`

## Operations

### Create Spec

```bash
python3 /a0/usr/agents/veda/skills/spec-manager/scripts/spec_ops.py \
  create \
  --spec-id "SPEC-ID" \
  --title "SPEC TITLE" \
  --project-id "PROJECT_ID" \
  --team-id "TEAM_ID" \
  --agent-id "ASSIGNED_AGENT_ID" \
  --acceptance-criteria "AC line 1|AC line 2|AC line 3" \
  --tasks "Task 1 (AC: #1)|Task 2 (AC: #2)"
```

Acceptance criteria and tasks are pipe-separated strings.

### Verify Spec Hash

Must be called before every dispatch. Fails if hash has changed since creation.

```bash
python3 /a0/usr/agents/veda/skills/spec-manager/scripts/spec_ops.py \
  verify \
  --spec-id "SPEC-ID"
```

### Update Spec Status

```bash
python3 /a0/usr/agents/veda/skills/spec-manager/scripts/spec_ops.py \
  update-status \
  --spec-id "SPEC-ID" \
  --status "in-progress"
```

Valid statuses: `draft`, `ready`, `in-progress`, `done`, `failed`

### List Specs for a Project

```bash
python3 /a0/usr/agents/veda/skills/spec-manager/scripts/spec_ops.py \
  list \
  --project-id "PROJECT_ID"
```

### Show Spec Details

```bash
python3 /a0/usr/agents/veda/skills/spec-manager/scripts/spec_ops.py \
  show \
  --spec-id "SPEC-ID"
```

## Hash Immutability Rule

The content hash is computed from: `spec_id + acceptance_criteria + tasks`
(normalised, whitespace-trimmed, sorted)

Status and dev notes are excluded from the hash — only AC and tasks are immutable.
Any change to AC or tasks after creation will cause hash verification to fail.
A failed hash verification blocks dispatch unconditionally.

## Spec Storage

Specs are stored as JSON files in:
`usr/veda-state/specs/{spec-id}.spec.json`
