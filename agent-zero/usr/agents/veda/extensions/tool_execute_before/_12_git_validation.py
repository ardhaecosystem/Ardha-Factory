import json
import os
import subprocess
from datetime import datetime, timezone
from python.helpers.extension import Extension

AUDIT_DIR = "/a0/usr/veda-state/audit"

# Tools that interact with the filesystem or execute code
CODE_TOOLS = {"code_execution_tool"}

# Git commands that modify remote state — require clean working tree
RISKY_GIT_PATTERNS = [
    "git push",
    "git commit",
    "git merge",
    "git rebase",
    "git reset --hard",
    "git checkout",
    "git branch -d",
    "git branch -D",
]


class VedaGitValidation(Extension):
    """
    Fired at tool_execute_before — before code_execution_tool runs.
    Checks if the agent is about to run a risky git command.
    If so, validates git working tree status.

    If working tree is dirty (uncommitted changes) before a git push/commit:
    - Injects a warning into tool_args["message"] (if present)
    - Does NOT block — injects strong advisory instead

    This is advisory enforcement. Hard blocking of git operations
    is deferred to the approval_gate extension (_14_).

    Only fires for subordinate agents (agent number > 0) with a spec assigned.
    Veda does not run code tools directly.
    """

    async def execute(self, tool_args=None, tool_name=None, **kwargs) -> None:
        if not tool_name or tool_name not in CODE_TOOLS:
            return

        # Only fire for subordinate agents with an active spec
        if self.agent.number == 0:
            return

        current_spec = self.agent.get_data("current_spec_id")
        if not current_spec:
            return

        if not tool_args:
            return

        # Extract the code/command being run
        code = tool_args.get("code", tool_args.get("body", ""))
        if not code:
            return

        # Check if this looks like a risky git operation
        code_lower = code.lower().strip()
        is_risky_git = any(pattern in code_lower for pattern in RISKY_GIT_PATTERNS)

        if not is_risky_git:
            return

        # Run git status check inside the container working directory
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd="/a0/usr/workdir"
            )
            git_output = result.stdout.strip()
            is_dirty = bool(git_output)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            # Git not available or timeout — skip check
            return

        agent_name = getattr(self.agent, "agent_name", "unknown")

        if is_dirty:
            warning = (
                f"\n[GIT VALIDATION WARNING] Working tree has uncommitted changes "
                f"before running: {code[:100]}...\n"
                f"Dirty files:\n{git_output[:500]}\n"
                f"Review uncommitted changes before pushing. "
                f"If intentional, proceed. If not, stash or commit first."
            )
            # Inject warning into tool args if there's a message field
            if "message" in tool_args:
                tool_args["message"] = tool_args["message"] + warning
            else:
                tool_args["_git_warning"] = warning

            print(
                f"[Veda:GitValidation] DIRTY TREE: agent={agent_name} "
                f"spec={current_spec} command={code[:80]}"
            )

            # Audit the event
            self._audit("git_dirty_tree_warning", agent_name, current_spec, code[:200])
        else:
            print(
                f"[Veda:GitValidation] CLEAN: agent={agent_name} "
                f"spec={current_spec} git status ok"
            )

    def _audit(self, event_type: str, agent_name: str, spec_id: str, details: str) -> None:
        try:
            os.makedirs(AUDIT_DIR, exist_ok=True)
            now = datetime.now(timezone.utc)
            date_str = now.strftime("%Y-%m-%d")
            audit_file = os.path.join(AUDIT_DIR, f"{date_str}.audit.jsonl")
            entry = {
                "timestamp": now.isoformat(),
                "event_type": event_type,
                "agent_name": agent_name,
                "agent_number": self.agent.number,
                "profile": getattr(self.agent.config, "profile", "unknown"),
                "spec_id": spec_id,
                "details": details,
            }
            with open(audit_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[Veda:GitValidation] WARN: Audit write failed: {e}")
