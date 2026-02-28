---
name: "restart-protocol"
description: "Prepares the Ardha Factory for a safe container restart. Checkpoints all state, signals restart_required, and generates operator notification. Use when new agent profiles have been forged or extension files have been modified."
version: "1.0.0"
author: "Ardha Factory"
tags: ["ardha", "orchestration", "restart", "checkpoint", "recovery"]
trigger_patterns:
  - "restart needed"
  - "restart required"
  - "checkpoint state"
  - "prepare restart"
  - "signal restart"
---

# Restart Protocol

Prepares the Ardha Factory for a safe container restart.
Only invoke after all active Specs have completed or been safely paused.

## When to Use

- After forging new agent profiles (they require restart to load into sys.modules)
- After modifying extension files
- When the restart_required flag is detected in the system prompt
- When papa explicitly requests a restart

## Pre-Restart Checklist

Before invoking this skill, verify:
1. No Specs are currently in-progress (check pipeline_state.json)
2. All active locks have been released
3. All sub-agents have completed their current task

## Operations

### Checkpoint All State

Writes a complete snapshot of current factory state and sets restart_required flag.

```bash
python3 /a0/usr/agents/veda/skills/restart-protocol/scripts/checkpoint_state.py \
  checkpoint \
  --reason "REASON_FOR_RESTART" \
  --pending-changes "CHANGE_1|CHANGE_2"
```

### Verify Checkpoint

Confirms all state files are valid JSON before restart.

```bash
python3 /a0/usr/agents/veda/skills/restart-protocol/scripts/checkpoint_state.py \
  verify
```

### Generate Operator Notification

Produces the message to show papa requesting the restart.

```bash
python3 /a0/usr/agents/veda/skills/restart-protocol/scripts/checkpoint_state.py \
  notify
```

## Post-Restart

After papa restarts the container:
- The `_30_veda_rehydrate.py` extension automatically runs on agent_init
- Expired locks are swept
- Interrupted specs are re-queued
- restart_required flag is cleared
- Extension mtime baseline is updated

No manual recovery steps are needed.

## Operator Restart Command

```bash
cd /home/deploy/ardha && docker compose restart
```
