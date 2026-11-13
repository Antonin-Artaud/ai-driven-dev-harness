---
title: 0007 — Specialist agents: UI designer under the builder, security and performance under the architect
status: accepted
date: 2026-11-13
supersedes: none
---
# 0007 — Specialist agents: UI designer under the builder, security and performance under the architect

## Context
The owner asked for a UI/UX designer builder and, like the architect, agents for security and performance/optimization. Up to 0.3.0 the architect applied security and performance checklists itself (`solution-design`), and the implementer coded every lot, UI included. Each extra agent run costs time and tokens, and the role rules of the hooks must cover every agent ([ADR 0006](./0006-validated-state-transitions.md)).

## Decision
- **`ui-ux-designer`**: a hidden builder subagent of the implementer's tier and tools. The architect marks each lot `Kind: ui` or `Kind: code`; the builder sends UI lots to the designer and the others to the implementer. Method in the `ui-ux-design` skill (design system first, WCAG 2.1 AA, every state, responsive, i18n, visual evidence). The hooks give it the implementer's rights.
- **`security-architect`** and **`performance-architect`**: design agents of the architect's tier, without shell or code writes. The architect runs them as subagents only when the brief's `Concerns` line or the change calls for it, and records `not consulted: <reason>` otherwise. Each writes only its own artifact (`security.md`, `performance.md`) with requirements per lot (`SEC-n`, `PERF-n`) and their severity if missed; the architect integrates them into `plan.md`. They stay user-invocable so the user can run a standalone analysis of an existing plan. Methods in the `security-design` and `performance-design` skills, which now hold the checklists moved from `solution-design`.
- **No second reviewer.** The single cross-family reviewer checks the `SEC-n` and `PERF-n` requirements of the plan and the UI section of the baseline checklist on UI lots, reporting a miss with the severity the plan gave.
- **"Optimisation"** is covered at design time only (budgets, hot paths, measurement plan). A post-build profiling or benchmarking pass is left as an open question.

## Consequences
- Specialist knowledge is applied where it is cheapest: before the code for security and performance, in the lot for UI.
- The plan becomes the single contract the reviewer checks; `security.md` and `performance.md` are local working files like the rest of `.ai/`.
- The hooks recognize three more subagents (agent type or marker). When the user runs a specialist directly, it is the main agent, so the hooks cannot stop the architect from writing `security.md` or `performance.md` (Known gaps).

## Alternatives considered
- Security and performance reviewers after the build — finds problems late, and doubles review cost on every workflow.
- One "quality architect" for both — two different methods and artifacts; harder to skip one when it is not needed.
- A UI designer that only writes specifications before the build — the owner asked for a builder; the UX intent in the brief and the plan already carries the specification.
- Consulting the specialists on every workflow — cost without benefit on small changes.
