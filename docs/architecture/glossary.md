---
title: Glossary
verified_on: 2026-11-25
sources:
  - skills/delivery-workflow/
  - README.md
---
# Glossary

| Term | Definition | Name in the code |
|---|---|---|
| Active workflow | Repository where `.ai/current` exists and the phase is not `done`; the only case where the hooks act | `load_workflow` |
| Slug | Identifier of the current work, kebab-case, at most 40 characters, prefixed with the work item ID | `.ai/current`, `state.slug`, `SLUG_RE` |
| Brief | Validated business need, with Given/When/Then acceptance criteria | `brief.md` |
| Plan | Implementation plan split into lots, with the documentation impact | `plan.md` |
| Lot | Coherent, testable increment that ends in one commit | lot |
| Lot dependencies | Lots a lot needs, or `none`; lots that change a common file are chained | `Depends on:` in `plan.md` |
| Wave | Lots whose dependencies are all integrated, run at the same time (at most the contract's `Parallel lots`) | `plan-execution` skill |
| Lot worktree | Git worktree of one lot of a wave, nested in the workflow folder, on a local lot branch | `.ai/<slug>/lot-<n>/`, `ai/<slug>--lot-<n>`, `lot_worktrees` |
| Integration | Rebase of a lot branch on the work branch, then fast-forward, worktree removed | `plan-execution` skill, lot gate in `stop.py` |
| Path | Triage result: `fast`, `standard` or `feature` | `state.path` |
| Handoff | Button that passes from one agent to another with a prefilled, unsent prompt (`send: false`) | `handoffs` |
| Review gate | Rule that requires an `APPROVED` review of HEAD and a clean working tree | `review_gate` |
| Draft PR | Unpublished Azure Repos PR; only the user publishes it | `isDraft: true` |
| Escalation | Legitimate stop of the workflow when the user must decide, with its origin phase and reason | `phase: escalated`, `state.escalation` |
| TDD cycle | Red-green-refactor evidence per behavior in the implementer's lot report: failing test, green run, refactor | `red-green-refactor` skill |
| Test-first gate | `PreToolUse` rule: a build or feedback commit that changes code without any test file asks the user | `evaluate_commit` |
| Validation | The user's explicit approval of the brief or the plan, recorded with its date and HEAD | `brief_validated`, `plan_validated` |
| Triage | Classification of the PR comments (fix, discuss, decline) before any change, in its own ungated phase | `phase: triage`, `feedback.md` |
| Close step | Script that ends a workflow: `phase: done`, archive under `.ai/archive/`, `.ai/current` removed | `scripts/close_workflow.py` |
| Hook state | Files only the hooks write: heartbeat, last user prompt, validation and escalation times, decision log | `.hooks.json`, `log.jsonl` |
| Heartbeat | Time and plugin version written by the hooks; the builder refuses to build without a fresh one | `touch_heartbeat` |
| Lot kind | `ui` lots go to the ui-ux-designer, `code` lots to the implementer | `Kind:` in `plan.md` |
| Specialist | security-architect or performance-architect, consulted by the architect when the brief's `Concerns` line or the change calls for it | `security.md`, `performance.md` |
| SEC-n, PERF-n | Security and performance requirements per lot, with the severity the reviewer uses if they are missed | `plan.md` |
| Plan deviation | Report from the implementer when the plan is wrong or impossible | `PLAN DEVIATION` |
| Project contract | "AI delivery workflow" section of `AGENTS.md`: commands, branch, parallel lots, Azure DevOps coordinates, architecture docs | `AGENTS.md` |
| Skill precedence | Project skills win over the plugin's skills | `delivery-workflow` skill |
| AI marker | `🤖` at the start of every comment posted by the workflow | `AI_MARKER` |
| Architecture map | `docs/architecture/` pages kept up to date by every workflow PR | `architecture-mapping` skill |
