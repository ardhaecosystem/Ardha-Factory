### veda_dispatch:
Ardha Factory pipeline dispatch tool.
Use this tool to delegate tasks to specialised sub-agents within the current pipeline stage.
Always specify the correct stage, agent name, task description, and project name.
Never dispatch to an agent outside the current active stage.
Never dispatch without a project name — this enforces memory isolation.

Valid stages and their agents:
- stage_1: planner, researcher, architect
- stage_2: documentation_formatter, ppt_designer, spec_architect, project_manager, project_state_manager, change_manager
- stage_3: frontend_developer, backend_developer, autonomous_agent_creator, github_maintainer, debugger, code_reviewer
- stage_4: cicd_engineer, qa_test_automation

usage:
~~~json
{
    "thoughts": [
        "I need to delegate the requirements analysis task to the planner sub-agent.",
        "This is stage_1. The planner is valid for this stage.",
        "Project is ardha-main. Memory isolation will be enforced."
    ],
    "headline": "Dispatching to planner — Stage 1",
    "tool_name": "veda_dispatch",
    "tool_args": {
        "stage": "stage_1",
        "agent": "planner",
        "task": "Analyse the client requirements and produce a structured project plan with milestones, deliverables, and risk assessment.",
        "project": "ardha-main"
    }
}
~~~
