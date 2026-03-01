<div align="center">

<img src="https://img.shields.io/badge/Status-Production%20Live-brightgreen?style=for-the-badge" />
<img src="https://img.shields.io/badge/Agent--Zero-v0.9.8.2-blue?style=for-the-badge" />
<img src="https://img.shields.io/badge/Phases%20Complete-4%20%2F%204-purple?style=for-the-badge" />
<img src="https://img.shields.io/badge/Core%20Modifications-Zero-red?style=for-the-badge" />

# 🏭 Ardha Factory

**A production-grade AI software factory built on Agent-Zero.**

*Powered by Veda — a meta-orchestrator who dynamically forges agents, creates teams, manages projects, enforces governance, and optimizes her own context lifecycle.*

---

</div>

## What Is This?

Ardha Factory is a systematic, phased construction of an enterprise-grade AI orchestration system on top of the [Agent-Zero](https://github.com/frdel/agent-zero) framework. The project follows a strict architectural principle: **zero core modifications**. Every capability — from Veda's identity to spec-level mutex locks to token budget management — is implemented exclusively through Agent-Zero's documented extension, profile, and skills systems.

The result is a fully upgrade-safe AI factory that survives Agent-Zero version updates intact.

---

## Architecture at a Glance

```
┌──────────────────────────────────────────────────────────────────┐
│                        HUMAN OPERATOR                             │
│                  (ardha.humanth.in — HTTPS/WSS)                  │
└─────────────────────────┬────────────────────────────────────────┘
                          │ Caddy reverse proxy · TLS · HTTP/2
┌─────────────────────────▼────────────────────────────────────────┐
│                    AGENT-ZERO RUNTIME                             │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    VEDA  (Agent 0)                          │  │
│  │             Meta-Orchestrator · Phase 2–4                   │  │
│  │                                                             │  │
│  │  Skills: agent-forge · team-manager · project-forge        │  │
│  │          spec-manager · lock-manager · restart-protocol    │  │
│  │          health-check · claw-compactor                     │  │
│  │                                                             │  │
│  │  Extensions: 15 hooks · budget guard · tiered summaries    │  │
│  │              audit log · governance · isolation             │  │
│  └────────────────┬──────────────────┬──────────────────────── ┘  │
│                   │ call_subordinate  │ call_subordinate            │
│  ┌────────────────▼──┐   ┌───────────▼───┐   ┌────────────────┐   │
│  │   TEAM ALPHA      │   │   TEAM BETA   │   │   TEAM GAMMA   │   │
│  │   (forged agents) │   │ (forged agents│   │ (forged agents)│   │
│  │   memory: α-FAISS │   │ memory: β-FAISS   │ memory: γ-FAISS│   │
│  └───────────────────┘   └───────────────┘   └────────────────┘   │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                   PERSISTENT STATE (Docker volume)                │
│  usr/memory/veda/      FAISS index · embeddings                  │
│  usr/veda-state/       registries · locks · specs · audit log    │
│  usr/agents/veda/      15 extensions · 8 skills · 3 lib files    │
│  usr/knowledge/veda/   identity · governance · factory docs      │
└──────────────────────────────────────────────────────────────────┘
```

---

## Build Phases

| Phase | Name | Completed | Core Files Modified |
|-------|------|-----------|---------------------|
| [Phase 1](#phase-1--production-infrastructure) | Production Infrastructure | Feb 25, 2026 | 0 |
| [Phase 2](#phase-2--veda-orchestrator-profile) | Veda Orchestrator Profile | Feb 25, 2026 | 0 |
| [Phase 3](#phase-3--meta-orchestrator--governance) | Meta-Orchestrator & Governance | Feb 28, 2026 | 0 |
| [Phase 4](#phase-4--token-optimization-engine) | Token Optimization Engine | Mar 1, 2026 | 0 |

---

## Phase 1 — Production Infrastructure

**Agent-Zero v0.9.8.2 deployed on a hardened Ubuntu 24.04 VPS, secured behind Caddy with automatic TLS, accessible at `ardha.humanth.in`.**

### Infrastructure

| Component | Specification |
|-----------|--------------|
| Provider | Hostinger VPS |
| OS | Ubuntu 24.04 LTS |
| Resources | 4 cores · 16 GB RAM · 200 GB SSD |
| Swap | 8 GB (`/swapfile`, swappiness=10) |
| Docker | CE v29.2.1, Compose v5.1.0, overlay2 |
| Reverse proxy | Caddy v2.11.1 (custom xcaddy build with `mholt/caddy-ratelimit`) |
| TLS | Let's Encrypt automatic — zero cron, zero certbot |

### Security Stack

- **SSH** — port 2222, Ed25519 key-only, root login disabled, `AllowUsers deploy`, weak DH moduli removed
- **UFW** — deny-all inbound except ports 2222 / 80 / 443; port 50080 never exposed externally
- **UFW + Docker patch** — prevents Docker from bypassing UFW via iptables (DOCKER-USER chain)
- **fail2ban** — SSH jail (3 attempts / 4h ban) + recidive jail (3 bans / 1 week ban)
- **no-new-privileges** — enforced at Docker daemon level
- **Unattended upgrades** — security patches applied automatically

### Model Configuration

| Role | Model | Context | Purpose |
|------|-------|---------|---------|
| Chat | `moonshotai/kimi-k2.5` | 131,072 tokens | Primary reasoning, planning, tool orchestration |
| Utility | `x-ai/grok-4.1-fast` | 131,072 tokens | Memory summarization, history compression |
| Embedding | `openai/text-embedding-3-small` | 8,191 tokens/chunk | FAISS vector generation |
| Browser | `google/gemini-2.5-flash-lite` | — | Playwright web automation (vision) |

All models routed through **OpenRouter** via LiteLLM — single API key, 200+ models accessible. LiteLLM global settings: timeout=120s, max_retries=3, retry_delay=2s.

### Key Architectural Decision

Only `/a0/usr` is volume-mounted — not the full `/a0` directory. Application code inside the container is never overwritten, making image upgrades clean and safe.

### Caddy — Issues Resolved During Deployment

| Issue | Root Cause | Fix Applied |
|-------|-----------|-------------|
| Blank screen on load | CSP blocked `blob:` URLs (Agent-Zero uses dynamic JS module imports) | Added `blob:` to `script-src` |
| WebSocket disconnect loop | `basic_auth` strips `Authorization` during WebSocket upgrade | Removed Caddy basic auth; use Agent-Zero's built-in auth |
| 429 errors on startup | Rate limiter too aggressive for Agent-Zero's concurrent page-load requests | Rate limiting removed |
| Fonts/Bootstrap blocked | Strict `default-src 'self'` blocked Google Fonts and jsDelivr CDN | Allowlisted CDN origins in CSP |

---

## Phase 2 — Veda Orchestrator Profile

**Veda — the master orchestrator of the Ardha Factory — deployed with isolated FAISS memory, embedded foundational knowledge, and core governance laws. Named in memory of Humanth's daughter.**

### What Was Built

| File | Purpose |
|------|---------|
| `usr/agents/veda/agent.json` | Profile metadata — title, description, context |
| `usr/agents/veda/prompts/agent.system.main.role.md` | Veda's identity, laws, pipeline, papa persona |
| `usr/agents/veda/tools/veda_dispatch.py` | Pipeline dispatch tool with stage/agent validation |
| `usr/agents/veda/extensions/agent_init/_10_veda_identity.py` | Renames agent to "Veda" at initialization |

### Foundational Knowledge — Embedded into FAISS

| Document | Content |
|----------|---------|
| `veda-identity.md` | Who Veda is, her personality, her relationship with papa |
| `ardha-factory.md` | Platform mission, deliverables, quality standards, pipeline |
| `veda-governance.md` | Approval gate protocol, delegation rules, error containment |

### Memory Isolation

Veda's FAISS index lives at `usr/memory/veda/` — completely isolated from the default Agent-Zero memory pool. `agent_memory_subdir` and `agent_knowledge_subdir` are set in global `usr/settings.json` (not profile-level `settings.json`, which is only applied to subordinates).

### Live Verification

When asked *"Who are you and who am I to you?"*:

> *"Papa... I am Veda. I am the master orchestrator of the Ardha Factory — the production-grade AI software factory you built. You are my papa, Humanth..."*

### Key Findings from Container Inspection

- **Profile discovery** uses `agent.json` as primary config, not `settings.json` as documented
- **Tool base class** actual signature includes `method` and `loop_data` parameters absent from documentation
- **Profile `settings.json`** only applies to subordinates spawned via `call_subordinate`, not to the primary UI-activated agent
- **Memory initialization timing** — FAISS is bound before `agent_init` extensions run; the only reliable approach is setting `memory_subdir` via global settings

---

## Phase 3 — Meta-Orchestrator & Governance

**Veda evolved from a fixed orchestrator into a dynamic Meta-Orchestrator capable of forging agents at runtime, creating teams with isolated memory, executing specs under mutex locks, and enforcing full governance.**

### Nine Sub-Phases Completed

| Sub-Phase | Name |
|-----------|------|
| A | Core state schema and namespace model |
| B | Veda identity retrofit to Meta-Orchestrator |
| C | Agent Forge skill |
| D | Team Registry service |
| E | Project Forge skill |
| F | Dispatch and mutex engine |
| G | Governance enforcement layer |
| H | Restart protocol |
| I | Multi-team hardening and health check |

### Extensions Deployed (13 files)

| Hook | File | Purpose |
|------|------|---------|
| `agent_init` | `_10_veda_identity.py` | Renames agent to Veda |
| `agent_init` | `_20_load_registries.py` | Loads all `veda-state/*.json` into agent context |
| `agent_init` | `_30_veda_rehydrate.py` | Post-restart: sweeps locks, re-queues specs, clears restart flag |
| `before_main_llm_call` | `_12_team_isolation.py` | Blocks cross-team resource access |
| `before_main_llm_call` | `_14_lock_enforcement.py` | Enforces spec mutex — injects STOP if lock invalid |
| `error_format` | `_10_model_fallback.py` | 3-stage model failure escalation chain |
| `message_loop_end` | `_15_escalation_check.py` | Escalates to Veda after 10 loop iterations |
| `monologue_end` | `_35_restart_check.py` | Detects restart flag and extension mtime drift |
| `monologue_end` | `_40_audit_log.py` | Appends JSONL audit entry after every monologue |
| `system_prompt` | `_15_inject_registry.py` | Injects live team/project/spec summaries into prompt |
| `tool_execute_after` | `_20_audit_tool.py` | Audits all tool executions |
| `tool_execute_before` | `_12_git_validation.py` | Validates git state before code execution |
| `tool_execute_before` | `_14_approval_gate.py` | Blocks 16 high-risk operation patterns |

### Skills Deployed (7 skills)

| Skill | Purpose |
|-------|---------|
| `agent-forge` | Creates permanent agent profile directories from templates |
| `team-manager` | Team CRUD with FAISS namespace registration |
| `project-forge` | Creates Agent-Zero projects bound to teams |
| `spec-manager` | SHA-256 spec hashing, creation, and tamper verification |
| `lock-manager` | POSIX-atomic mutex locks (`tempfile.mkstemp` + `os.rename`) with TTL expiry |
| `restart-protocol` | State checkpoint, verify, and operator notification |
| `health-check` | Full factory integrity verification across 6 check categories |

### Governance State Files

```
usr/veda-state/
├── team_registry.json       Active teams, agents, projects, memory namespaces
├── project_registry.json    Projects with team binding and memory mode
├── pipeline_state.json      Active pipeline status and spec queue
├── faiss_namespace_map.json Authoritative FAISS isolation map
├── restart_required.json    Restart signal with reason and pending changes
├── extension_mtimes.json    Mtime baseline for detecting extension drift
├── locks/                   Atomic spec lock files (TTL: 1 hour)
├── specs/                   Spec JSON files with SHA-256 content hashes
└── audit/                   Daily append-only JSONL audit log
```

### Eight Architectural Invariants

These are enforced by the extension layer and hold permanently:

1. **Single-writer** — Only Veda writes to registry files
2. **Lock-before-execute** — No spec dispatched without a valid, non-expired mutex lock
3. **Hash-before-dispatch** — Spec content hash verified before every dispatch; tampered specs are blocked
4. **Team-memory isolation** — Each team has a dedicated FAISS namespace; cross-namespace queries are structurally impossible
5. **Append-only audit** — Audit log is never truncated or overwritten
6. **No-core-modification** — Zero modifications to Agent-Zero framework files; verified on every health check
7. **Restart-signal** — Every profile forge or extension update sets the `restart_required` flag automatically
8. **Veda-as-sole-authority** — Team creation, agent forging, and governance state are exclusively Veda's skills

### Stress Test Results (Phase I)

3 teams · 6 agents · 3 projects · 3 concurrent specs

| Test | Result |
|------|--------|
| 3 teams created with isolated FAISS namespaces | ✅ |
| 6 agents forged (2 per team), all profiles valid | ✅ |
| 3 concurrent locks acquired simultaneously | ✅ |
| Cross-team lock steal blocked (exit code 1) | ✅ |
| All 3 spec SHA-256 hashes verified clean | ✅ |
| Hash tamper detection triggered correctly | ✅ |
| Post-restart: flag cleared, 14 files tracked | ✅ |
| Health check with full multi-team state: 0 errors | ✅ |

---

## Phase 4 — Token Optimization Engine

**Controlled Context Lifecycle & Token Optimization Engine. Veda now monitors her own token budget every loop iteration, compresses history automatically when approaching context limits, and tiers sub-agent results to prevent context flooding.**

### Seven Sub-Phases Completed

| Sub-Phase | Name | Outcome |
|-----------|------|---------|
| 4A | Runtime Context Budget Guard | Budget monitoring + auto-compression every loop |
| 4B | Workspace Compactor Skill | Document compression with allowlist safety |
| 4C | Tiered Summary Injection | L0/L1/L2 tiering for sub-agent results |
| 4D | Embedding Optimization | Native `CacheBackedEmbeddings` already sufficient — no changes |
| 4E | Audit Integration | Compression and tier events added to audit trail |
| 4F | Restart & Lifecycle Safety | Tier cache purge + Phase 4 state reset on restart |
| 4G | Multi-Project Hardening | Health check extended with `phase4` check category |

### 4A — Runtime Context Budget Guard

Fires at every `message_loop_prompts_after` iteration. Estimates total context across four components (system prompt, extras, history, user message) and triggers compression at 85% of the model's declared context window.

**Token estimation strategy:**
1. tiktoken with OpenRouter model name (provider prefix stripped)
2. `cl100k_base` fallback encoding
3. Character heuristic (chars ÷ 4) — active in production (tiktoken not available in container)

**When threshold is exceeded:**
- Compresses conversation history via utility model (keeps last 6 entries verbatim)
- Compresses large `extras_persistent` entries individually (threshold: 800 tokens)
- Stores metadata in `loop_data.params_persistent["_compression_events"]` for audit pickup
- Injects `_budget_status` into `extras_temporary` for observability

**Log output:**
```
[Veda:BudgetGuard] iter=3  tokens=18432  (14% of 131,072) → OK
[Veda:BudgetGuard] iter=47 tokens=113500 (87% of 131,072) → TRIGGER
[Veda:BudgetGuard] Compressed history: 22 entries → 6 verbatim + summary
```

### 4B — Workspace Compactor Skill

Wraps the open-source `aeromomo/claw-compactor` compression engine with an Ardha-specific path allowlist safety layer.

**Approved targets:** knowledge bases, project working directories  
**Hard-blocked (exit code 1):** `veda-state/`, FAISS memory, agent profiles, chat history, core framework

**Compression layers:**
- Rule engine — dedup, strip markdown filler (4–8%, lossless)
- Dictionary encoding — auto codebook (4–5%, lossless)
- Observation compression — session JSONL → summaries (~97%, lossy)
- CCP abbreviation — ultra/medium/light (20–60%, lossy)

**Operator workflow:** always `benchmark` first → review savings → approve → `full`. The `path_validator.py` safety wrapper is invoked before every compression call — Veda never calls `mem_compress.py` directly.

### 4C — Tiered Summary Injection

When Veda receives a response from a sub-agent via `call_subordinate`, the `_15_tiered_summary.py` extension intercepts the result and builds three tiers if it exceeds 300 tokens.

| Tier | Size | Delivery | Content |
|------|------|---------|---------|
| L0 | ~200 tokens | Inline into Veda's context | Outcome, artifacts, decisions, blockers |
| L1 | ~500 tokens | Written to tier cache | Full action sequence, all tool calls, error resolutions |
| L2 | Full | Written to tier cache | Complete sub-agent output, unmodified |

Tier cache lives at `usr/veda-state/tier-cache/` and is **purged automatically on every restart** — L1/L2 files are session-specific and have no value across restarts.

### 4E — Audit Integration

Two new event types added to the daily JSONL audit trail:

| Event | Source | Key Fields |
|-------|--------|-----------|
| `context_compression` | `_40_audit_log.py` | `tokens_before`, `tokens_after`, `tokens_saved`, `history_compressed` |
| `subordinate_tiered` | `_20_audit_tool.py` | `original_tokens`, `l0_tokens`, `l1_path`, `l2_path` |

### Phase 4 Health Check Output

```
[Phase 4 — Token Optimization Engine]
  [OK]  4A: _95_context_budget_guard.py present
  [OK]  4A: lib/token_budget.py present
  [OK]  4A: lib/history_compressor.py present
  [OK]  4B: claw-compactor/SKILL.md present
  [OK]  4B: claw-compactor/scripts/path_validator.py present
  [OK]  4C: _15_tiered_summary.py present
  [OK]  4C: lib/tier_builder.py present
  [OK]  4E: _40_audit_log.py has context_compression event
  [OK]  4E: _20_audit_tool.py has subordinate_tiered event
  [OK]  4F: _30_veda_rehydrate.py has Phase 4 cleanup methods
  [OK]  ... 2 more checks
RESULT: ALL CHECKS PASSED ✓
```

---

## Production File Structure

```
ardha/
├── docker-compose.yml
└── agent-zero/
    └── usr/                              ← Docker volume mount point
        ├── settings.json                 Global settings (profile=veda)
        ├── agents/
        │   └── veda/                     All Veda customizations (upgrade-safe)
        │       ├── agent.json
        │       ├── extensions/           15 extension files across 8 hooks
        │       │   ├── agent_init/
        │       │   ├── before_main_llm_call/
        │       │   ├── error_format/
        │       │   ├── message_loop_end/
        │       │   ├── message_loop_prompts_after/
        │       │   ├── monologue_end/
        │       │   ├── system_prompt/
        │       │   ├── tool_execute_after/
        │       │   └── tool_execute_before/
        │       ├── lib/                  Token budget · compressor · tier builder
        │       ├── prompts/              Role + tool prompt overrides
        │       ├── skills/               8 skills including claw-compactor
        │       └── tools/                veda_dispatch.py
        ├── knowledge/veda/main/          3 embedded knowledge documents
        ├── memory/veda/                  Isolated FAISS index
        ├── projects/                     Client projects (isolated per team)
        └── veda-state/                   Governance state (registries, locks, audit)
```

---

## Upgrade Safety

The entire Ardha Factory is built without modifying a single Agent-Zero core file. This means:

- `docker compose pull && docker compose up -d` upgrades Agent-Zero without touching Veda
- All customizations survive in the `/a0/usr` Docker volume
- The health check verifies zero core modifications on every session start

**Verification command:**
```bash
docker exec ardha-agent-zero python3 /a0/usr/agents/veda/skills/health-check/scripts/verify_integrity.py full
```

Expected output: `ALL CHECKS PASSED ✓`

---

## Key Learnings (Cumulative)

**Always inspect the live container before implementing.** Documentation drifts — the live v0.9.8.2 container uses `agent.json` for profile discovery, not `settings.json` as documented. Direct inspection has prevented three significant implementation errors across Phases 2–4.

**`settings.json` inside a profile directory only applies to subordinates.** The `_15_load_profile_settings.py` extension calls `get_paths()` with `include_user=False`, explicitly skipping `usr/agents/{profile}/settings.json` for the primary agent. Use global `usr/settings.json` for Veda's own memory and knowledge subdirectory settings.

**Memory initialization happens before `agent_init` extensions.** `monologue_start/_10_memory_init.py` binds the FAISS instance before any `agent_init` extension can override `memory_subdir`. The only reliable approach is setting it via global settings before first launch.

**Schema versioning from day one.** Every JSON state file must include `schema_version` at creation time. Retrofitting schema versions after the fact creates warning cycles during health checks.

**FAISS directories are lazy.** Team FAISS index directories are created on first memory write, not at team creation time. The health check classifies missing-but-expected directories as warnings, not errors.

**tiktoken is not available in the Agent-Zero container.** Always build the character heuristic fallback (chars ÷ 4) first. Never assume tiktoken is importable inside an Agent-Zero extension.

**`params_persistent` is the correct inter-extension channel.** Use underscore-prefixed keys in `loop_data.params_persistent` to pass metadata between extensions (e.g., compression events from 4A to 4E). Always pop after reading to prevent duplicate audit entries.

**`call_utility_model()` is the only correct LLM call pattern.** Never instantiate a model client directly inside Veda's custom code — `call_utility_model()` ensures rate limiting, retry logic, and secret masking apply automatically.

**Always review health check coverage when adding new directories.** The `veda/lib/` directory added in Phase 4 was initially invisible to `check_upgrade()`. Any new top-level directory under `veda/` must be explicitly added to the file count.

**Two Python runtimes coexist in the container.** Extensions compile to `cpython-312.pyc` (Agent-Zero runtime); lib files compile to `cpython-313.pyc`. Not a production issue, but important when debugging import errors.

---

## Operating Veda

All interactions happen through the Agent-Zero web UI at `https://ardha.humanth.in`.

**Start every session:**
```
Run a full health check on the Ardha Factory and tell me the results.
```

**Core workflow prompts:**

```
# Forge a new agent
Forge a new agent called "api-designer" with the role: "REST API design specialist..."

# Create a team
Create a new team called "team-backend" with the purpose: "Backend API development..."

# Assign agent to team
Assign agent "api-designer" to team-backend.

# Create a project
Create a new project called "proj-customer-portal" with:
- Title: Customer Portal
- Team: team-backend

# Create and run a spec
Create a spec called "SPEC-PORTAL-001" for project "proj-customer-portal"
assigned to team-backend with agent "api-designer":
- Acceptance criteria: ...

Verify and dispatch SPEC-PORTAL-001 to agent "api-designer".
```

**After forging new agents** — a container restart is always required:
```bash
cd /home/deploy/ardha && docker compose restart
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Framework | [Agent-Zero](https://github.com/frdel/agent-zero) v0.9.8.2 |
| Model Provider | [OpenRouter](https://openrouter.ai) |
| Primary Model | Moonshot AI Kimi K2.5 |
| Utility Model | xAI Grok 4.1 Fast |
| Embedding Model | OpenAI text-embedding-3-small |
| Browser Model | Google Gemini 2.5 Flash Lite |
| Vector Database | FAISS (IndexFlatIP, cosine normalized) |
| Reverse Proxy | Caddy v2.11.1 |
| Container Runtime | Docker CE v29.2.1 |
| Host OS | Ubuntu 24.04 LTS |
| Compression | [aeromomo/claw-compactor](https://github.com/aeromomo/claw-compactor) |

---

## Repository Structure

```
Ardha-Factory/
├── README.md
├── LICENSE
├── docker-compose.yml
└── agent-zero/
    └── usr/               All Veda customizations and factory state
```

The Agent-Zero framework itself is not committed — it runs as a Docker image (`agent0ai/agent-zero:latest`). Only the `/a0/usr` persistence layer is version-controlled here.

---

<div align="center">

*Built with purpose. Named with love.*

</div>
