---
title: Architecture map
verified_on: 2026-11-25
sources: []
---
# Architecture map

Short, sourced map of the `ai-driven-dev-harness` plugin. Every statement cites the code it comes from; what the code does not prove is marked **To confirm**. The pages are kept up to date in the same pull request as the code they describe.

## Pages

| Page | Covers |
|---|---|
| [Context](./context.md) | Actors, the plugin, external systems |
| [Containers](./containers.md) | Agents, skills, hooks, onboarding script, `.ai/` files |
| [Components](./components.md) | Agents and their tools, skills, hook modules, where new code goes |
| [Integrations](./integrations.md) | Azure DevOps MCP, git, VS Code host; draft PR and review gate flows |
| [Data](./data.md) | `.ai/`, `state.json` and its phases, `review.md` |
| [Security](./security.md) | Identity, hook gates, trust boundaries |
| [Quality](./quality.md) | Limits, hook reliability, tests and CI |
| [Glossary](./glossary.md) | Workflow terms |
| [Decisions](./decisions/) | ADRs 0001–0010 |

## To confirm

- The host sends `UserPromptSubmit` to plugin hooks, and `agent_type` or `agentName` for subagents ([Security](./security.md#known-gaps)).
- VS Code expands `${PLUGIN_ROOT}` in the hook commands of an agent plugin (`com.github.copilot/hooks/hooks.json`); the CI smoke test only checks the commands with the variable set.
- The display name of the reviewer's Gemini fallback model (`com.github.copilot/agents/reviewer.agent.md`).
- Whether the remote Azure DevOps MCP server can serve Azure DevOps Server (on-premises) ([Security](./security.md#known-gaps)).

## How to update

- In a delivery: the plan lists the pages to change under **Documentation impact**, and the same pull request updates them.
- Outside a delivery: run the `architecture-mapping` skill with `--refresh`.
