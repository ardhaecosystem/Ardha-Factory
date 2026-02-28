import json
import os
from python.helpers.extension import Extension

VEDA_STATE_DIR = "/a0/usr/veda-state"
TEAM_REGISTRY_FILE = os.path.join(VEDA_STATE_DIR, "team_registry.json")
FAISS_NAMESPACE_FILE = os.path.join(VEDA_STATE_DIR, "faiss_namespace_map.json")


class VedaTeamIsolation(Extension):
    """
    Fired before every LLM call (before_main_llm_call hook).
    Enforces team memory namespace isolation for Veda.

    Checks:
    1. If Veda is operating as orchestrator (agent number 0), skip isolation check
       — Veda has authority over all namespaces for registry reads.
    2. If a subordinate agent has a team assignment, verify it is only referencing
       its own team's memory namespace.
    3. Injects a namespace reminder into loop_data.extras_temporary so the LLM
       is always aware of its isolation boundary.
    """

    async def execute(self, loop_data=None, **kwargs) -> None:
        if loop_data is None:
            return

        agent_number = self.agent.number
        registries = self.agent.get_data("registries")

        # --- Veda (agent 0) is the orchestrator ---
        # She reads all registries but never writes to other namespaces directly.
        # Inject a lightweight reminder of her namespace authority.
        if agent_number == 0:
            faiss_map = self._load_faiss_map(registries)
            active_ns = [
                ns_id for ns_id, ns in faiss_map.get("namespaces", {}).items()
                if ns.get("status") == "active"
            ]
            if not hasattr(loop_data, "extras_temporary"):
                return
            loop_data.extras_temporary["veda_namespace_context"] = (
                f"[NAMESPACE AUTHORITY] You are Veda. "
                f"Active FAISS namespaces: {active_ns}. "
                f"You may READ registry data from all namespaces. "
                f"You may NOT write to any namespace except 'veda'. "
                f"Sub-agents are restricted to their assigned team namespace only."
            )
            return

        # --- Subordinate agents ---
        # Determine this agent's assigned namespace from the team registry.
        agent_name = getattr(self.agent.config, "profile", None)
        if not agent_name:
            return

        assigned_namespace = self._get_assigned_namespace(agent_name, registries)
        if not assigned_namespace:
            # Standalone agent — inject warning, no hard block
            if hasattr(loop_data, "extras_temporary"):
                loop_data.extras_temporary["veda_namespace_context"] = (
                    f"[NAMESPACE] You are '{agent_name}' (standalone). "
                    f"You have no team namespace assigned. "
                    f"Do not access any team memory namespace. "
                    f"Your memory scope is limited to the default namespace."
                )
            return

        # Inject namespace constraint into prompt
        if hasattr(loop_data, "extras_temporary"):
            loop_data.extras_temporary["veda_namespace_context"] = (
                f"[NAMESPACE CONSTRAINT] You are '{agent_name}'. "
                f"Your assigned memory namespace: '{assigned_namespace}'. "
                f"You must ONLY access memory within namespace '{assigned_namespace}'. "
                f"Cross-namespace access is FORBIDDEN. "
                f"If you need data outside your namespace, escalate to Veda."
            )

        # Log to container logs for audit visibility
        print(
            f"[Veda:IsolationCheck] agent={agent_name} "
            f"namespace={assigned_namespace} agent_number={agent_number}"
        )

    def _load_faiss_map(self, registries: dict) -> dict:
        """Load FAISS map from registries cache or disk."""
        if registries and registries.get("faiss_namespace_map"):
            return registries["faiss_namespace_map"]
        if os.path.exists(FAISS_NAMESPACE_FILE):
            with open(FAISS_NAMESPACE_FILE) as f:
                return json.load(f)
        return {}

    def _get_assigned_namespace(self, agent_name: str, registries: dict) -> str | None:
        """Look up the agent's assigned team namespace from team registry."""
        team_reg = None
        if registries and registries.get("team_registry"):
            team_reg = registries["team_registry"]
        elif os.path.exists(TEAM_REGISTRY_FILE):
            with open(TEAM_REGISTRY_FILE) as f:
                team_reg = json.load(f)

        if not team_reg:
            return None

        for team_id, team in team_reg.get("teams", {}).items():
            if (
                team.get("status") == "active"
                and agent_name in team.get("agents", [])
            ):
                return team.get("memory_subdir", team_id)

        return None
