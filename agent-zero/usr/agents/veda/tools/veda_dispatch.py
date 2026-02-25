from python.helpers.tool import Tool, Response


class VedaDispatch(Tool):
    """
    Ardha Factory pipeline dispatch tool.
    Veda uses this to delegate tasks to named sub-agents within the current stage.
    All delegations are logged. Stage boundaries are enforced.
    """

    # Valid sub-agents per stage
    PIPELINE = {
        "stage_1": ["planner", "researcher", "architect"],
        "stage_2": ["documentation_formatter", "ppt_designer", "spec_architect",
                    "project_manager", "project_state_manager", "change_manager"],
        "stage_3": ["frontend_developer", "backend_developer", "autonomous_agent_creator",
                    "github_maintainer", "debugger", "code_reviewer"],
        "stage_4": ["cicd_engineer", "qa_test_automation"],
    }

    async def execute(self, **kwargs) -> Response:
        stage    = self.args.get("stage", "").strip()
        agent    = self.args.get("agent", "").strip()
        task     = self.args.get("task", "").strip()
        project  = self.args.get("project", "").strip()

        # --- Validation ---
        if not stage or not agent or not task:
            return Response(
                message="[Veda Dispatch] ERROR: 'stage', 'agent', and 'task' are all required.",
                break_loop=False,
            )

        valid_agents = self.PIPELINE.get(stage, [])
        if not valid_agents:
            return Response(
                message=f"[Veda Dispatch] ERROR: Unknown stage '{stage}'. Valid stages: {list(self.PIPELINE.keys())}",
                break_loop=False,
            )

        if agent not in valid_agents:
            return Response(
                message=f"[Veda Dispatch] ERROR: Agent '{agent}' does not belong to {stage}. Valid agents: {valid_agents}",
                break_loop=False,
            )

        if not project:
            return Response(
                message="[Veda Dispatch] ERROR: 'project' is required to enforce memory isolation.",
                break_loop=False,
            )

        # --- Build delegation message ---
        delegation = (
            f"[Ardha Factory — {stage.upper()} | Project: {project}]\n\n"
            f"You are '{agent}', a specialised sub-agent of the Ardha Factory.\n"
            f"Operate strictly within project scope: {project}\n"
            f"Do NOT access memory or knowledge from other projects.\n\n"
            f"Your task:\n{task}"
        )

        # --- Log the dispatch ---
        self.agent.context.log.log(
            type="info",
            heading=f"Veda: Dispatching to {agent} [{stage}] — Project: {project}",
            content=task,
        )

        return Response(
            message=delegation,
            break_loop=False,
        )
