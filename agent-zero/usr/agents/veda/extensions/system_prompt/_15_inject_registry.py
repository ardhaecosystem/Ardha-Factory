import json
from python.helpers.extension import Extension


class VedaInjectRegistry(Extension):
    """
    Fired at system_prompt assembly.
    Injects a structured summary of Veda's live registry state
    into the system prompt so the LLM always has current context.

    Injects into: loop_data.extras_persistent["veda_registry_context"]

    Content injected:
    - Health check status (errors and warnings from agent_init)
    - restart_required flag status
    - Active teams summary (count, IDs, agent counts)
    - Active projects summary (count, IDs, bound teams)
    - Pipeline state (status, current spec, queue depth)
    - FAISS namespace summary (registered namespaces)
    """

    async def execute(self, system_prompt: list, **kwargs) -> None:
        registries = self.agent.get_data("registries")
        health = self.agent.get_data("veda_health")

        # If registries failed to load entirely, inject a critical warning
        if not registries:
            system_prompt.append(
                "\n## [VEDA REGISTRY STATUS: CRITICAL]\n"
                "Registry files could not be loaded at startup.\n"
                "Do NOT proceed with any dispatch or registry mutation.\n"
                "Report this to papa immediately.\n"
            )
            return

        lines = ["\n## [VEDA REGISTRY STATUS]"]

        # --- Health check summary ---
        if health:
            errors = health.get("errors", [])
            warnings = health.get("warnings", [])
            if errors:
                lines.append(f"ERRORS ({len(errors)}):")
                for e in errors:
                    lines.append(f"  - {e}")
            if warnings:
                lines.append(f"WARNINGS ({len(warnings)}):")
                for w in warnings:
                    lines.append(f"  - {w}")
            if not errors and not warnings:
                lines.append("Health: OK — all registries loaded, no anomalies.")

        # --- Restart required ---
        restart = registries.get("restart_required")
        if restart and restart.get("required") is True:
            lines.append(
                f"!! RESTART REQUIRED: {restart.get('reason')} "
                f"(triggered at {restart.get('triggered_at')})"
            )
            lines.append(
                "!! Do NOT dispatch any newly forged agents until papa restarts the container."
            )

        # --- Team registry summary ---
        team_reg = registries.get("team_registry")
        if team_reg and team_reg.get("teams"):
            teams = team_reg["teams"]
            active = {k: v for k, v in teams.items() if v.get("status") == "active"}
            lines.append(f"Teams: {len(active)} active of {len(teams)} total")
            for tid, t in active.items():
                agent_count = len(t.get("agents", []))
                project_count = len(t.get("projects", []))
                lines.append(
                    f"  - {tid}: {agent_count} agent(s), "
                    f"{project_count} project(s), "
                    f"memory={t.get('memory_subdir', 'unset')}"
                )
        else:
            lines.append("Teams: none registered yet.")

        # --- Project registry summary ---
        proj_reg = registries.get("project_registry")
        if proj_reg and proj_reg.get("projects"):
            projects = proj_reg["projects"]
            active = {
                k: v for k, v in projects.items() if v.get("status") == "active"
            }
            lines.append(f"Projects: {len(active)} active of {len(projects)} total")
            for pid, p in active.items():
                spec_count = len(p.get("specs", []))
                lines.append(
                    f"  - {pid}: team={p.get('team_id', 'unbound')}, "
                    f"{spec_count} spec(s)"
                )
        else:
            lines.append("Projects: none registered yet.")

        # --- Pipeline state summary ---
        pipeline = registries.get("pipeline_state")
        if pipeline:
            status = pipeline.get("status", "unknown")
            current = pipeline.get("current_spec", "none")
            queue_depth = len(pipeline.get("queue", []))
            failed = len(pipeline.get("failed_specs", []))
            lines.append(
                f"Pipeline: status={status}, "
                f"current_spec={current}, "
                f"queued={queue_depth}, "
                f"failed={failed}"
            )
        else:
            lines.append("Pipeline: state unavailable.")

        # --- FAISS namespace summary ---
        faiss = registries.get("faiss_namespace_map")
        if faiss and faiss.get("namespaces"):
            ns_list = list(faiss["namespaces"].keys())
            lines.append(f"FAISS namespaces: {ns_list}")
        else:
            lines.append("FAISS namespaces: only 'veda' registered.")

        lines.append(
            "Consult full registry files in usr/veda-state/ "
            "for complete details before any dispatch or mutation."
        )

        # --- Inject into system prompt ---
        system_prompt.append("\n".join(lines))
