import json
import os
from datetime import datetime, timezone
from python.helpers.tool import Tool, Response

VEDA_STATE_DIR = "/a0/usr/veda-state"
TEAM_REGISTRY_FILE = os.path.join(VEDA_STATE_DIR, "team_registry.json")
AGENT_REGISTRY_FILE = os.path.join(VEDA_STATE_DIR, "agent_registry.json")
LOCKS_DIR = os.path.join(VEDA_STATE_DIR, "locks")
LOCK_TTL_SECONDS = 3600


class VedaDispatch(Tool):
    """
    Ardha Factory registry-driven dispatch tool.
    Replaces the Phase 2 hardcoded pipeline dispatcher.

    Validates against live registries before every dispatch:
    - Agent must exist in agent_registry.json
    - Agent must be assigned to the specified team
    - Spec lock must be held by Veda before dispatching
    - Memory namespace is enforced from team registry

    Args:
        agent_id  — target agent profile name (from agent_registry.json)
        team_id   — team the agent belongs to
        project_id — project context for memory isolation
        spec_id   — Spec being executed (for lock validation)
        task      — task description to send to the sub-agent
        reset     — "true" to create fresh sub-agent, "false" to reuse (default: "true")
    """

    async def execute(self, **kwargs) -> Response:
        agent_id = self.args.get("agent_id", "").strip()
        team_id = self.args.get("team_id", "").strip()
        project_id = self.args.get("project_id", "").strip()
        spec_id = self.args.get("spec_id", "").strip()
        task = self.args.get("task", "").strip()
        reset = self.args.get("reset", "true").strip().lower() == "true"

        # --- Basic argument validation ---
        missing = [k for k, v in {
            "agent_id": agent_id,
            "team_id": team_id,
            "project_id": project_id,
            "spec_id": spec_id,
            "task": task
        }.items() if not v]

        if missing:
            return Response(
                message=f"[Veda Dispatch] ERROR: Missing required args: {missing}",
                break_loop=False
            )

        # --- Load registries ---
        agent_reg = self._load_json(AGENT_REGISTRY_FILE)
        team_reg = self._load_json(TEAM_REGISTRY_FILE)

        # --- Validate agent exists ---
        agents = agent_reg.get("agents", {})
        if agent_id not in agents:
            return Response(
                message=(
                    f"[Veda Dispatch] ERROR: Agent '{agent_id}' not found in agent_registry.json. "
                    f"Forge the agent first using the agent-forge skill. "
                    f"Available agents: {list(agents.keys())}"
                ),
                break_loop=False
            )

        agent_entry = agents[agent_id]

        # --- Validate agent is assigned to specified team ---
        agent_team = agent_entry.get("team_id")
        if agent_team != team_id:
            return Response(
                message=(
                    f"[Veda Dispatch] ERROR: Agent '{agent_id}' is assigned to team "
                    f"'{agent_team}', not '{team_id}'. "
                    f"Use the correct team_id or reassign the agent via team-manager."
                ),
                break_loop=False
            )

        # --- Validate agent status ---
        agent_status = agent_entry.get("status", "")
        if agent_status not in ("assigned", "active"):
            return Response(
                message=(
                    f"[Veda Dispatch] ERROR: Agent '{agent_id}' has status '{agent_status}'. "
                    f"Only 'assigned' or 'active' agents can be dispatched."
                ),
                break_loop=False
            )

        # --- Validate team exists and is active ---
        teams = team_reg.get("teams", {})
        if team_id not in teams:
            return Response(
                message=f"[Veda Dispatch] ERROR: Team '{team_id}' not found in team_registry.json.",
                break_loop=False
            )
        if teams[team_id].get("status") != "active":
            return Response(
                message=f"[Veda Dispatch] ERROR: Team '{team_id}' is not active.",
                break_loop=False
            )

        # --- Validate lock is held for this spec ---
        lock = self._load_lock(spec_id)
        if not lock:
            return Response(
                message=(
                    f"[Veda Dispatch] ERROR: No lock held for Spec '{spec_id}'. "
                    f"Acquire the lock via lock-manager before dispatching."
                ),
                break_loop=False
            )
        if self._is_expired(lock):
            return Response(
                message=(
                    f"[Veda Dispatch] ERROR: Lock for Spec '{spec_id}' has expired. "
                    f"Re-acquire the lock via lock-manager before dispatching."
                ),
                break_loop=False
            )

        # --- Get memory namespace from team ---
        memory_namespace = teams[team_id].get("memory_subdir", team_id)

        # --- Build delegation message ---
        delegation = (
            f"[ARDHA FACTORY DISPATCH]\n"
            f"Spec ID: {spec_id}\n"
            f"Project: {project_id}\n"
            f"Team: {team_id}\n"
            f"Memory namespace: {memory_namespace}\n\n"
            f"CONSTRAINTS:\n"
            f"- Operate strictly within memory namespace '{memory_namespace}'\n"
            f"- Do not access memory or knowledge from other namespaces\n"
            f"- Do not create subordinate agents\n"
            f"- Do not modify registry files\n"
            f"- Report results in structured format\n"
            f"- Escalate blockers to Veda immediately — do not proceed past failures\n\n"
            f"TASK:\n{task}"
        )

        # --- Log the dispatch ---
        self.agent.context.log.log(
            type="info",
            heading=f"Veda: Dispatching to '{agent_id}' [Team: {team_id}] Spec: {spec_id}",
            content=task,
        )

        print(
            f"[Veda:Dispatch] agent={agent_id} team={team_id} "
            f"project={project_id} spec={spec_id} namespace={memory_namespace}"
        )

        # --- Create or reuse subordinate agent ---
        from agent import Agent, UserMessage
        from initialize import initialize_agent

        existing_sub = self.agent.get_data(Agent.DATA_NAME_SUBORDINATE)
        if existing_sub is None or reset:
            sub_config = initialize_agent()
            sub_config.profile = agent_id
            sub_config.memory_subdir = memory_namespace
            sub_agent = Agent(
                self.agent.number + 1,
                sub_config,
                self.agent.context
            )
            self.agent.set_data(Agent.DATA_NAME_SUBORDINATE, sub_agent)
            sub_agent.set_data(Agent.DATA_NAME_SUPERIOR, self.agent)
            sub_agent.set_data("current_spec_id", spec_id)
        else:
            sub_agent = existing_sub

        # --- Send task to subordinate ---
        sub_agent.hist_add_user_message(UserMessage(message=delegation, attachments=[]))
        response = await sub_agent.monologue()

        # Seal topic for compression
        sub_agent.history.new_topic()

        return Response(
            message=response or f"[Veda Dispatch] Agent '{agent_id}' completed task for Spec '{spec_id}'.",
            break_loop=False
        )

    def _load_json(self, path: str) -> dict:
        if not os.path.exists(path):
            return {}
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _load_lock(self, spec_id: str) -> dict | None:
        safe = spec_id.replace("/", "-").replace("\\", "-").replace(" ", "-")
        path = os.path.join(LOCKS_DIR, f"{safe}.lock.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _is_expired(self, lock: dict) -> bool:
        locked_at = lock.get("locked_at_ts", 0)
        ttl = lock.get("ttl_seconds", LOCK_TTL_SECONDS)
        now = datetime.now(timezone.utc).timestamp()
        return (now - locked_at) > ttl
