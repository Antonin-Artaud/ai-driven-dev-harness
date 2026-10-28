---
name: solution-design
description: 'Design an implementation plan from a validated brief: map the existing architecture, compare 2-3 options, challenge the user''s technical vision, apply architecture, design pattern, security, performance, testing and reliability checklists, record an ADR, and write plan.md split into lots and tasks. Use for architecture decisions, technical design, design patterns, threat or performance analysis, and implementation planning.'
---

# Solution design

Goal: a plan that an implementer without access to this conversation can execute lot by lot, and that a reviewer can check the code against.

## Procedure

1. **Check the input.** Read `.ai/current`, `state.json` and `brief.md`. The brief must be validated; otherwise use the **Revisit the business need** handoff. Set `phase: design`.
2. **Map the existing architecture first.** Find the modules, patterns, conventions and tests the change touches, and how similar problems are already solved in this codebase. Consistency with the existing code beats a theoretically better pattern.
3. **Load the relevant standards** following the skill precedence of the `delivery-workflow` skill: the project's architecture, security and performance skills and instructions first. Use these checklists only for topics no project standard covers, and only those the change actually touches:
   - [Design principles and patterns](./references/design-principles.md)
   - [Security](./references/security.md)
   - [Performance](./references/performance.md)
   - [Testing strategy](./references/testing-strategy.md)
   - [Reliability and observability](./references/reliability-observability.md)
4. **Generate options:** 2 or 3 for the `standard` and `feature` paths, always including the minimal change that satisfies the acceptance criteria. If the user stated a technical vision, evaluate it as one of the options and propose at least one credible alternative. Compare them: fit with the existing code, complexity, risk, performance, security, testability, reversibility.
5. **Decide** in ADR form (context, decision, consequences) and list the non-goals.
6. **Challenge the user's vision explicitly.** List each point where you disagree, with evidence (code, constraints, numbers), and ask the user to decide. Never silently pick their option or yours.
7. **Slice into lots.** A lot is a coherent, independently testable increment that ends in one commit (typically up to about 300 changed lines). Order the lots so the build stays green after each one. Each task names the files, the change and its done criterion. Map every acceptance criterion to at least one test.
8. **Record the risks** (likelihood, impact, mitigation) and the rollback strategy.
9. **Self-check:** could an implementer execute lot 1 with only `plan.md`, `brief.md` and the repository? Are the build and test commands known? If not, complete the plan.
10. **Write `plan.md`** from the [plan template](./assets/plan-template.md) and ask the user to validate it. Iterate until they agree, then point them to the **Implement the plan** handoff. If the design shows that the need itself is unclear, use **Revisit the business need** instead.

## Guardrails against over-engineering

- YAGNI: no abstraction, extension point or pattern without a concrete force in the brief or the existing code.
- No new dependency, service or infrastructure without explaining why the existing stack cannot do it.
- Prefer boring, well-known solutions and changes that are easy to revert.
- Performance work needs a target or a measured problem; otherwise keep it simple and measurable.

## Constraints

- Never modify source code or Azure DevOps. Only write files under `.ai/`.
- The plan says precisely *what* and *where*, and *how* only where the choice matters.
