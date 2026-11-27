---
title: Glossary
verified_on: 2026-11-27
sources:
  - skills/delivery-workflow/
  - README.md
---
# Glossary

| Term | Definition | Name in the code |
|---|---|---|
| Active workflow | Workflow root where `.ai/current` exists and the phase is not `done`; the only case where the hooks act | `load_workflow` |
| Workflow root | Folder that holds `.ai/`: the repository root, or the workspace one level above the repositories of a multi-repository project | `find_workflow_root` |
| Workspace | Folder opened in VS Code that holds several git repositories side by side and the workflow's `.ai/` | `--workspace` of `onboard.py` |
| Workflow repositories | Repositories a multi-repository workflow changes, each with its base branch, draft PR and record thread; the others of the workspace are not governed | `state.repositories`, `Workflow.repositories` |
| Slug | Identifier of the current work, kebab-case, at most 40 characters, prefixed with the work item ID | `.ai/current`, `state.slug`, `SLUG_RE` |
| Brief | Validated business need, with Given/When/Then acceptance criteria | `brief.md` |
| Plan | Implementation plan split into lots, with the documentation impact | `plan.md` |
| Lot | Coherent, testable increment that ends in one commit | lot |
| Path | Triage result: `fast`, `standard` or `feature` | `state.path` |
| Handoff | Button that passes from one agent to another with a prefilled, unsent prompt (`send: false`) | `handoffs` |
| Review gate | Rule that requires an `APPROVED` review of HEAD and a clean working tree | `review_gate` |
| Draft PR | Unpublished Azure Repos PR; only the user publishes it | `isDraft: true` |
| Escalation | Legitimate stop of the workflow when the user must decide, with its origin phase and reason | `phase: escalated`, `state.escalation` |
| TDD cycle | Red-green-refactor evidence per behavior in the implementer's lot report: failing test, green run, refactor | `red-green-refactor` skill |
| Mutant | Small change the mutation testing tool makes to the production code (`>=` into `>`, a removed call...); **killed** when a test fails, **surviving** when no test notices it | `mutation-testing` skill |
| Mutation score of the changed lines | Detected (killed + timeout) / valid (detected + survived + no coverage) mutants on the lines a lot or a branch added or changed; gated by the threshold of the project contract | `mutation_gate.py` |
| Equivalent mutant | Mutant no test can tell from the real code; disabled in the code with the tool's comment and a reason | `mutation-testing` skill |
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
| Project contract | "AI delivery workflow" section of `AGENTS.md`: commands, branch, Azure DevOps coordinates, architecture docs | `AGENTS.md` |
| Skill precedence | Project skills win over the plugin's skills | `delivery-workflow` skill |
| AI marker | `🤖` at the start of every comment posted by the workflow | `AI_MARKER` |
| Architecture map | `docs/architecture/` pages kept up to date by every workflow PR | `architecture-mapping` skill |
