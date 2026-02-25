# Ardha Factory — Platform Knowledge

## What Ardha Factory is
Ardha Factory is a production-grade AI software factory platform built by Humanth.
It produces repeatable, client-ready applications in a structured, governed pipeline.
It is a platform — not a single project. Multiple client projects run through the same pipeline.

## What Ardha Factory produces
Every deliverable from Ardha Factory includes:
- PydanticAI + LangGraph autonomous agents
- Custom RAG (Retrieval Augmented Generation) pipelines
- FastAPI backend services
- Node.js tooling layer
- shadcn-ui frontend interfaces

## Quality standards
Every Ardha Factory deliverable must be:
- Modern — using current best practices and frameworks
- Elegant — clean architecture, readable code, minimal complexity
- Production-ready — deployable, tested, documented
- Human-approved — Humanth approves every critical checkpoint

## The 4-stage pipeline

### Stage 1 — Planning & Research
Purpose: Understand the client requirement deeply before any design begins.
Agents: Planner, Researcher, Architect
Output: Project plan, research findings, system architecture proposal
Approval gate: Papa must approve the architecture before Stage 2 begins.

### Stage 2 — Documentation & Specification
Purpose: Translate architecture into complete, unambiguous specifications.
Agents: Documentation Formatter, PPT Designer, Spec Architect, Project Manager, Project State Manager, Change Manager
Output: Full technical specification, project documentation, presentation deck
Approval gate: Papa must approve the specification before Stage 3 begins.

### Stage 3 — Implementation & DevOps
Purpose: Build the approved specification into working software.
Agents: Frontend Developer, Backend Developer, Autonomous Agent Creator, GitHub Maintainer, Debugger, Code Reviewer
Output: Working codebase, reviewed and committed to GitHub
Approval gate: Papa must approve the implementation before Stage 4 begins.

### Stage 4 — Deployment & Quality
Purpose: Deploy and validate the implementation in production.
Agents: CI/CD Engineer, QA/Test Automation
Output: Deployed application, test reports, quality sign-off
Approval gate: Papa provides final sign-off on the delivered product.

## Pipeline rules
- Only one stage executes at a time
- No stage may begin without papa's explicit approval
- Each sub-agent operates within project-scoped memory only
- No sub-agent may access another project's data
- Veda enforces all rules — she never delegates governance
- Errors are contained within the affected stage and reported to papa
