### veda_dispatch
Ardha Factory registry-driven dispatch tool.
Use this tool to delegate Spec work to a registered sub-agent.

**Pre-dispatch checklist (mandatory):**
1. Verify spec hash integrity using spec-manager skill
2. Acquire mutex lock using lock-manager skill
3. Then call this tool

**Required args:**
- `agent_id` — agent profile name from agent_registry.json
- `team_id` — team the agent is assigned to
- `project_id` — project context for memory isolation
- `spec_id` — Spec ID being executed
- `task` — structured task description including AC references

**Optional args:**
- `reset` — "true" (default) to create fresh sub-agent, "false" to reuse existing

**Validation performed automatically:**
- Agent must exist in agent_registry.json
- Agent must be assigned to the specified team
- Team must be active
- Spec lock must be held and not expired

**Example:**
~~~json
{
    "thoughts": [
        "Papa approved SPEC-team-frontend-proj-dashboard-001.",
        "Hash verified. Lock acquired for this spec.",
        "Dispatching to 'frontend-dev' agent in team-frontend."
    ],
    "headline": "Dispatching SPEC-team-frontend-proj-dashboard-001 to frontend-dev",
    "tool_name": "veda_dispatch",
    "tool_args": {
        "agent_id": "frontend-dev",
        "team_id": "team-frontend",
        "project_id": "proj-dashboard",
        "spec_id": "SPEC-team-frontend-proj-dashboard-001",
        "task": "Spec: SPEC-team-frontend-proj-dashboard-001\nAC #1: Login form renders correctly\nAC #2: Form validates required fields\nTask 1 (AC: #1): Create LoginForm component\nTask 2 (AC: #2): Add validation logic",
        "reset": "true"
    }
}
~~~
