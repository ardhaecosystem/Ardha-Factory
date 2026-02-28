---
name: "health-check"
description: "Verifies the integrity of the entire Ardha Factory state. Checks registry consistency, orphan detection, FAISS namespace alignment, lock hygiene, spec integrity, and upgrade safety. Run at session start and after any major operation."
version: "1.0.0"
author: "Ardha Factory"
tags: ["ardha", "orchestration", "health-check", "integrity", "monitoring"]
trigger_patterns:
  - "health check"
  - "verify integrity"
  - "system health"
  - "factory status"
  - "check system"
  - "run health check"
---

# Health Check

Verifies the integrity of the entire Ardha Factory state.
Run at session start, after restart, and after any major operation.

## When to Use

- At the start of every session
- After container restart
- After forging new agents or teams
- After completing a pipeline run
- When something seems wrong

## Operations

### Full Health Check (recommended)

```bash
python3 /a0/usr/agents/veda/skills/health-check/scripts/verify_integrity.py full
```

### Individual Checks

```bash
# Registry consistency only
python3 /a0/usr/agents/veda/skills/health-check/scripts/verify_integrity.py registries

# Orphan detection (agents/teams/projects with broken references)
python3 /a0/usr/agents/veda/skills/health-check/scripts/verify_integrity.py orphans

# Lock hygiene (expired locks, orphan lock files)
python3 /a0/usr/agents/veda/skills/health-check/scripts/verify_integrity.py locks

# FAISS namespace alignment
python3 /a0/usr/agents/veda/skills/health-check/scripts/verify_integrity.py faiss

# Upgrade safety (confirm zero core file modifications)
python3 /a0/usr/agents/veda/skills/health-check/scripts/verify_integrity.py upgrade
```

## Exit Codes

- `0` — All checks passed
- `1` — One or more warnings (non-critical)
- `2` — One or more errors (action required)

## Interpreting Results

- `[OK]` — Check passed
- `[WARN]` — Non-critical issue, monitor
- `[ERROR]` — Action required, report to papa
