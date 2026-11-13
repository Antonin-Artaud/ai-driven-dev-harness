---
title: 0001 — The method lives in skills, agents stay thin
status: accepted
date: 2026-11-13
supersedes: none
---
# 0001 — The method lives in skills, agents stay thin

Backfilled on 2026-11-13 from the design of 0.1.0 (`README.md`, `com.github.copilot/agents/`, `skills/`).

## Context
The workflow has five agents (challenger, architect, builder, implementer, reviewer) and a method that must evolve: procedures, templates, checklists. Target projects already have their own conventions and skills, which must win over the plugin's.

## Decision
Each agent file only holds its role, its tools, its model, its handoffs and a short list of constraints, and loads skills (`delivery-workflow`, `business-challenge`, `solution-design`, `plan-execution`, `code-review`, `pr-feedback`, `azure-devops`, `architecture-mapping`, `project-onboarding`). Skills follow a precedence rule: project skills first, plugin checklists only for topics no project skill covers.

## Consequences
- The method is portable (the skill format is shared across hosts) and testable for structure (`tests/test_plugin_structure.py`).
- A project changes the behaviour by adding skills, without forking the plugin; PR learnings land in project skills (`pr-feedback`).
- Skills are prose: what must not depend on the model's compliance goes to hooks ([ADR 0003](./0003-standard-library-python-hooks.md), [ADR 0006](./0006-validated-state-transitions.md)).

## Alternatives considered
- Long agent prompts holding the method — duplicated between agents, not reusable by projects.
- Project-specific forks of the plugin — every improvement would have to be merged by hand.
