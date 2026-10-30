---
title: Architecture map
verified_on: 2026-10-30
sources: []
---
# Architecture map

Short, sourced map of the `ai-delivery-workflow` plugin. Every statement cites the code it comes from; what the code does not prove is marked **To confirm**. The pages are kept up to date in the same pull request as the code they describe.

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
| [Decisions](./decisions/) | ADRs (none yet) |

## To confirm

None.

## How to update

- In a delivery: the plan lists the pages to change under **Documentation impact**, and the same pull request updates them.
- Outside a delivery: run the `architecture-mapping` skill with `--refresh`.
