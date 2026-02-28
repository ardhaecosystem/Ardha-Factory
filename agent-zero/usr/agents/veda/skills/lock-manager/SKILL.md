---
name: "lock-manager"
description: "Acquires, releases, checks, and cleans up spec-level mutex locks for the Ardha Factory. Use before dispatching any Spec to an agent, and after Spec completion. Prevents concurrent execution of the same Spec."
version: "1.0.0"
author: "Ardha Factory"
tags: ["ardha", "orchestration", "lock-manager", "mutex", "spec"]
trigger_patterns:
  - "acquire lock"
  - "release lock"
  - "check lock"
  - "spec lock"
  - "lock manager"
  - "cleanup locks"
---

# Lock Manager

Manages spec-level mutex locks for deterministic Spec execution.
Only Veda may invoke this skill. Never dispatch a Spec without first acquiring its lock.

## When to Use

- **Before dispatching a Spec** — acquire the lock
- **After Spec completion or failure** — release the lock
- **Before checking if a Spec is available** — check lock status
- **On session start or after restart** — cleanup expired locks

## Operations

### Acquire Lock

Must be called before every Spec dispatch. Fails if lock already held by another agent.

```bash
python3 /a0/usr/agents/veda/skills/lock-manager/scripts/lock_ops.py \
  acquire \
  --spec-id "SPEC-ID" \
  --agent-id "AGENT_ID" \
  --team-id "TEAM_ID" \
  --project-id "PROJECT_ID"
```

### Release Lock

Must be called after Spec completion (success or failure).

```bash
python3 /a0/usr/agents/veda/skills/lock-manager/scripts/lock_ops.py \
  release \
  --spec-id "SPEC-ID" \
  --agent-id "AGENT_ID"
```

### Check Lock Status

Returns current lock holder and expiry for a Spec.

```bash
python3 /a0/usr/agents/veda/skills/lock-manager/scripts/lock_ops.py \
  check \
  --spec-id "SPEC-ID"
```

### Cleanup Expired Locks

Run on session start or after restart to reclaim expired locks.

```bash
python3 /a0/usr/agents/veda/skills/lock-manager/scripts/lock_ops.py \
  cleanup
```

### List All Locks

```bash
python3 /a0/usr/agents/veda/skills/lock-manager/scripts/lock_ops.py \
  list
```

## Lock TTL

Default TTL: **3600 seconds (1 hour)**.
Expired locks are automatically reclaimable by any agent.
TTL prevents deadlocks if a container restart interrupts an executing agent.

## Invariants

- A Spec may only have ONE active lock at a time
- Only the lock holder may release the lock
- Veda must acquire the lock BEFORE dispatching to the agent
- Veda must release the lock AFTER the agent reports completion
- Expired locks (TTL exceeded) are treated as released
