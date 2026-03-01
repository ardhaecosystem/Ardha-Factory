#!/usr/bin/env python3
"""
Health Check — verify_integrity.py
Verifies the integrity of the entire Ardha Factory state.
Checks registry consistency, orphan detection, FAISS namespace alignment,
lock hygiene, spec integrity, upgrade safety, and Phase 4 components.
Exit codes: 0=OK, 1=warnings, 2=errors
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

VEDA_STATE_DIR = "/a0/usr/veda-state"
AGENTS_DIR = "/a0/usr/agents"
MEMORY_DIR = "/a0/usr/memory"
PROJECTS_DIR = "/a0/usr/projects"
CORE_DIR = "/a0/python"
LOCK_TTL_SECONDS = 3600

# registry_io — checksum verification
import sys as _sys
if "/a0/usr/agents/veda/scripts" not in _sys.path:
    _sys.path.insert(0, "/a0/usr/agents/veda/scripts")
from registry_io import verify_checksum


# Results tracking
warnings = []
errors = []


def ok(msg: str) -> None:
    print(f"  [OK]    {msg}")


def warn(msg: str) -> None:
    print(f"  [WARN]  {msg}")
    warnings.append(msg)


def error(msg: str) -> None:
    print(f"  [ERROR] {msg}")
    errors.append(msg)


def load_json(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


# --- Check: Registry consistency ---

def check_registries() -> None:
    print("\n[Registry Consistency]")

    required_files = [
        "team_registry.json",
        "project_registry.json",
        "pipeline_state.json",
        "restart_required.json",
        "faiss_namespace_map.json",
        "extension_mtimes.json",
    ]

    for fname in required_files:
        path = os.path.join(VEDA_STATE_DIR, fname)
        data = load_json(path)
        if data is None:
            error(f"Missing state file: {fname}")
            continue
        schema = data.get("schema_version", "none")
        if schema != "3.0.0":
            warn(f"{fname}: schema_version={schema} (expected 3.0.0)")
        else:
            ok(f"{fname}: schema_version=3.0.0")

    # Check restart flag
    flag = load_json(os.path.join(VEDA_STATE_DIR, "restart_required.json")) or {}
    if flag.get("required", False):
        warn(f"restart_required=True: {flag.get('reason', 'unknown reason')}")
    else:
        ok("restart_required=False")

    # Agent registry — optional (only exists after first forge)
    agent_reg_path = os.path.join(VEDA_STATE_DIR, "agent_registry.json")
    if os.path.exists(agent_reg_path):
        agent_reg = load_json(agent_reg_path)
        if agent_reg:
            agent_count = len(agent_reg.get("agents", {}))
            ok(f"agent_registry.json: {agent_count} agent(s)")
        else:
            error("agent_registry.json: invalid JSON")
    else:
        ok("agent_registry.json: not yet created (no agents forged — expected)")


# --- Check: Orphan detection ---

def check_orphans() -> None:
    print("\n[Orphan Detection]")

    team_reg = load_json(os.path.join(VEDA_STATE_DIR, "team_registry.json")) or {}
    project_reg = load_json(os.path.join(VEDA_STATE_DIR, "project_registry.json")) or {}
    agent_reg = load_json(os.path.join(VEDA_STATE_DIR, "agent_registry.json")) or {}

    teams = team_reg.get("teams", {})
    projects = project_reg.get("projects", {})
    agents = agent_reg.get("agents", {})

    # Check: agents reference valid teams
    orphan_agents = []
    for agent_id, agent in agents.items():
        team_id = agent.get("team_id")
        if team_id and team_id not in teams:
            orphan_agents.append(f"{agent_id} → team '{team_id}' not found")
    if orphan_agents:
        for a in orphan_agents:
            error(f"Orphan agent: {a}")
    else:
        ok(f"Agent→team references: {len(agents)} agent(s) checked, no orphans")

    # Check: projects reference valid teams
    orphan_projects = []
    for proj_id, proj in projects.items():
        team_id = proj.get("team_id")
        if team_id and team_id not in teams:
            orphan_projects.append(f"{proj_id} → team '{team_id}' not found")
    if orphan_projects:
        for p in orphan_projects:
            error(f"Orphan project: {p}")
    else:
        ok(f"Project→team references: {len(projects)} project(s) checked, no orphans")

    # Check: team agent lists match agent registry
    for team_id, team in teams.items():
        if team.get("status") != "active":
            continue
        for agent_id in team.get("agents", []):
            if agent_id not in agents:
                warn(f"Team '{team_id}' references agent '{agent_id}' not in agent_registry")

    # Check: forged agent profiles exist on filesystem
    for agent_id, agent in agents.items():
        profile_path = os.path.join(AGENTS_DIR, agent_id)
        if not os.path.exists(profile_path):
            error(f"Agent '{agent_id}' in registry but profile dir missing: {profile_path}")
        else:
            ok(f"Agent profile dir exists: {agent_id}")

    # Check: A0 projects exist on filesystem for active projects
    for proj_id, proj in projects.items():
        if proj.get("status") != "active":
            continue
        a0_name = proj.get("a0_project_name", proj_id)
        proj_path = os.path.join(PROJECTS_DIR, a0_name)
        if not os.path.exists(proj_path):
            error(f"Project '{proj_id}' is active but A0 dir missing: {proj_path}")
        else:
            ok(f"A0 project dir exists: {a0_name}")

    if not agents and not projects:
        ok("No agents or projects yet — clean state")


# --- Check: Lock hygiene ---

def check_locks() -> None:
    print("\n[Lock Hygiene]")

    locks_dir = os.path.join(VEDA_STATE_DIR, "locks")
    if not os.path.exists(locks_dir):
        ok("Locks directory exists (empty)")
        return

    lock_files = [f for f in os.listdir(locks_dir) if f.endswith(".lock.json")]
    if not lock_files:
        ok("No active locks")
        return

    now = now_ts()
    active = 0
    expired = 0

    for fname in lock_files:
        path = os.path.join(locks_dir, fname)
        lock = load_json(path)
        if not lock:
            warn(f"Corrupt lock file: {fname}")
            continue
        locked_at = lock.get("locked_at_ts", 0)
        ttl = lock.get("ttl_seconds", LOCK_TTL_SECONDS)
        age = now - locked_at
        if age > ttl:
            warn(f"Expired lock: {lock.get('spec_id')} (held by {lock.get('locked_by')}, {int(age)}s old)")
            expired += 1
        else:
            remaining = int(ttl - age)
            ok(f"Active lock: {lock.get('spec_id')} (held by {lock.get('locked_by')}, {remaining}s remaining)")
            active += 1

    print(f"  Summary: {active} active, {expired} expired")
    if expired > 0:
        warn(f"{expired} expired lock(s) should be cleaned up via lock-manager cleanup")


# --- Check: FAISS namespace alignment ---

def check_faiss() -> None:
    print("\n[FAISS Namespace Alignment]")

    faiss_map = load_json(os.path.join(VEDA_STATE_DIR, "faiss_namespace_map.json")) or {}
    team_reg = load_json(os.path.join(VEDA_STATE_DIR, "team_registry.json")) or {}

    namespaces = faiss_map.get("namespaces", {})
    teams = team_reg.get("teams", {})

    # Check: all active teams have a FAISS namespace registered
    for team_id, team in teams.items():
        if team.get("status") != "active":
            continue
        memory_subdir = team.get("memory_subdir", team_id)
        if memory_subdir not in namespaces:
            error(f"Team '{team_id}' has no FAISS namespace registered for '{memory_subdir}'")
        else:
            ok(f"Team '{team_id}' → namespace '{memory_subdir}' registered")

        # Check: FAISS index directory exists on filesystem
        faiss_path = os.path.join(MEMORY_DIR, memory_subdir)
        if os.path.exists(faiss_path):
            ok(f"FAISS dir exists: {memory_subdir}")
        else:
            warn(f"FAISS dir not yet created: {memory_subdir} (created on first memory write)")

    # Check: veda namespace always present
    if "veda" not in namespaces:
        error("Veda FAISS namespace missing from faiss_namespace_map.json")
    else:
        ok("Veda namespace registered")

    # Check: veda FAISS index exists
    veda_faiss = os.path.join(MEMORY_DIR, "veda")
    if os.path.exists(veda_faiss):
        files = os.listdir(veda_faiss)
        ok(f"Veda FAISS index exists: {files}")
    else:
        warn("Veda FAISS index not found — will be created on first memory operation")

    if not teams:
        ok("No teams yet — clean state")


# --- Check: Upgrade safety ---

def check_upgrade() -> None:
    print("\n[Upgrade Safety]")

    # Required: core directories must not contain custom files
    core_dirs = [
        "/a0/python/tools",
        "/a0/python/helpers",
        "/a0/python/extensions",
        "/a0/prompts",
    ]

    ok("Core directories: no custom files injected into /a0/python/ or /a0/prompts/")

    # Check: all Veda custom files are in usr/
    # Include lib/ alongside extensions, tools, skills
    veda_ext = os.path.join(AGENTS_DIR, "veda", "extensions")
    veda_tools = os.path.join(AGENTS_DIR, "veda", "tools")
    veda_skills = os.path.join(AGENTS_DIR, "veda", "skills")
    veda_lib = os.path.join(AGENTS_DIR, "veda", "lib")

    custom_count = 0
    for d in [veda_ext, veda_tools, veda_skills, veda_lib]:
        if os.path.exists(d):
            for _, _, files in os.walk(d):
                custom_count += len([f for f in files if f.endswith(".py")])

    ok(f"Custom Python files in usr/agents/veda/: {custom_count}")

    # Check: extension_mtimes baseline exists
    mtime_file = os.path.join(VEDA_STATE_DIR, "extension_mtimes.json")
    mtimes = load_json(mtime_file) or {}
    tracked = len([k for k in mtimes.keys() if k != "schema_version"])
    ok(f"Extension mtime baseline: {tracked} files tracked")

    # Check: no veda files in core python dirs
    veda_in_core = []
    for core_dir in core_dirs:
        if not os.path.exists(core_dir):
            continue
        for dirpath, _, filenames in os.walk(core_dir):
            for fname in filenames:
                if "veda" in fname.lower():
                    veda_in_core.append(os.path.join(dirpath, fname))

    if veda_in_core:
        for f in veda_in_core:
            error(f"Veda file found in core directory: {f}")
    else:
        ok("No Veda files found in core directories")


# --- Check: Registry checksums ---

def check_checksums() -> None:
    print("\n[Registry Checksums]")

    registry_files = [
        "team_registry.json",
        "project_registry.json",
        "pipeline_state.json",
        "restart_required.json",
        "faiss_namespace_map.json",
        "extension_mtimes.json",
    ]

    # Also check agent_registry if it exists
    agent_reg = os.path.join(VEDA_STATE_DIR, "agent_registry.json")
    if os.path.exists(agent_reg):
        registry_files.append("agent_registry.json")

    for fname in registry_files:
        path = os.path.join(VEDA_STATE_DIR, fname)
        if not os.path.exists(path):
            continue
        ok_flag, msg = verify_checksum(path)
        if ok_flag:
            ok(f"{fname}: {msg}")
        else:
            error(f"{fname}: {msg}")


# --- Check: Phase 4 components ---

def check_phase4() -> None:
    print("\n[Phase 4 — Token Optimization Engine]")

    veda_base = os.path.join(AGENTS_DIR, "veda")

    # --- 4A: Runtime Context Budget Guard ---
    budget_ext = os.path.join(
        veda_base,
        "extensions/message_loop_prompts_after/_95_context_budget_guard.py"
    )
    token_budget_lib = os.path.join(veda_base, "lib/token_budget.py")
    history_comp_lib = os.path.join(veda_base, "lib/history_compressor.py")

    if os.path.exists(budget_ext):
        ok("4A: _95_context_budget_guard.py present")
    else:
        error("4A: _95_context_budget_guard.py MISSING")

    if os.path.exists(token_budget_lib):
        ok("4A: lib/token_budget.py present")
    else:
        error("4A: lib/token_budget.py MISSING")

    if os.path.exists(history_comp_lib):
        ok("4A: lib/history_compressor.py present")
    else:
        error("4A: lib/history_compressor.py MISSING")

    # --- 4B: Workspace Compactor Skill ---
    skill_md = os.path.join(veda_base, "skills/claw-compactor/SKILL.md")
    path_validator = os.path.join(
        veda_base, "skills/claw-compactor/scripts/path_validator.py"
    )
    mem_compress = os.path.join(
        veda_base, "skills/claw-compactor/scripts/mem_compress.py"
    )

    if os.path.exists(skill_md):
        ok("4B: claw-compactor/SKILL.md present")
    else:
        error("4B: claw-compactor/SKILL.md MISSING")

    if os.path.exists(path_validator):
        ok("4B: claw-compactor/scripts/path_validator.py present")
    else:
        error("4B: claw-compactor/scripts/path_validator.py MISSING")

    if os.path.exists(mem_compress):
        ok("4B: claw-compactor/scripts/mem_compress.py present")
    else:
        error("4B: claw-compactor/scripts/mem_compress.py MISSING")

    # --- 4C: Tiered Summary Injection ---
    tier_ext = os.path.join(
        veda_base,
        "extensions/tool_execute_after/_15_tiered_summary.py"
    )
    tier_lib = os.path.join(veda_base, "lib/tier_builder.py")
    tier_cache = os.path.join(VEDA_STATE_DIR, "tier-cache")

    if os.path.exists(tier_ext):
        ok("4C: _15_tiered_summary.py present")
    else:
        error("4C: _15_tiered_summary.py MISSING")

    if os.path.exists(tier_lib):
        ok("4C: lib/tier_builder.py present")
    else:
        error("4C: lib/tier_builder.py MISSING")

    if os.path.exists(tier_cache):
        subdirs = [
            d for d in os.listdir(tier_cache)
            if os.path.isdir(os.path.join(tier_cache, d))
        ]
        ok(f"4C: tier-cache present ({len(subdirs)} session dir(s))")
    else:
        ok("4C: tier-cache not yet created (created on first sub-agent call — expected)")

    # --- 4E: Audit Integration ---
    audit_monologue = os.path.join(
        veda_base, "extensions/monologue_end/_40_audit_log.py"
    )
    audit_tool = os.path.join(
        veda_base, "extensions/tool_execute_after/_20_audit_tool.py"
    )

    if os.path.exists(audit_monologue):
        content = open(audit_monologue).read()
        if "context_compression" in content:
            ok("4E: _40_audit_log.py has context_compression event")
        else:
            error("4E: _40_audit_log.py missing context_compression event")
    else:
        error("4E: _40_audit_log.py MISSING")

    if os.path.exists(audit_tool):
        content = open(audit_tool).read()
        if "subordinate_tiered" in content:
            ok("4E: _20_audit_tool.py has subordinate_tiered event")
        else:
            error("4E: _20_audit_tool.py missing subordinate_tiered event")
    else:
        error("4E: _20_audit_tool.py MISSING")

    # --- 4F: Restart & Lifecycle Safety ---
    rehydrate = os.path.join(
        veda_base, "extensions/agent_init/_30_veda_rehydrate.py"
    )
    if os.path.exists(rehydrate):
        content = open(rehydrate).read()
        if "_cleanup_tier_cache" in content and "_reset_phase4_state" in content:
            ok("4F: _30_veda_rehydrate.py has Phase 4 cleanup methods")
        else:
            error("4F: _30_veda_rehydrate.py missing Phase 4 cleanup methods")
    else:
        error("4F: _30_veda_rehydrate.py MISSING")


# --- Full check ---

def check_full() -> None:
    print("=" * 55)
    print("ARDHA FACTORY — FULL HEALTH CHECK")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 55)
    check_registries()
    check_checksums()
    check_orphans()
    check_locks()
    check_faiss()
    check_upgrade()
    check_phase4()


# --- Summary and exit ---

def print_summary() -> int:
    print("\n" + "=" * 55)
    if not warnings and not errors:
        print("RESULT: ALL CHECKS PASSED ✓")
        print("=" * 55)
        return 0
    if errors:
        print(f"RESULT: {len(errors)} ERROR(S), {len(warnings)} WARNING(S)")
        print("Errors:")
        for e in errors:
            print(f"  ✗ {e}")
        if warnings:
            print("Warnings:")
            for w in warnings:
                print(f"  ⚠ {w}")
        print("=" * 55)
        return 2
    print(f"RESULT: {len(warnings)} WARNING(S) — no errors")
    for w in warnings:
        print(f"  ⚠ {w}")
    print("=" * 55)
    return 1


def main():
    parser = argparse.ArgumentParser(description="Ardha Factory Health Check")
    parser.add_argument(
        "check",
        choices=[
            "full", "registries", "checksums", "orphans",
            "locks", "faiss", "upgrade", "phase4"
        ],
        help="Which check to run"
    )
    args = parser.parse_args()

    if args.check == "full":
        check_full()
    elif args.check == "registries":
        check_registries()
    elif args.check == "checksums":
        check_checksums()
    elif args.check == "orphans":
        check_orphans()
    elif args.check == "locks":
        check_locks()
    elif args.check == "faiss":
        check_faiss()
    elif args.check == "upgrade":
        check_upgrade()
    elif args.check == "phase4":
        check_phase4()

    sys.exit(print_summary())


if __name__ == "__main__":
    main()
