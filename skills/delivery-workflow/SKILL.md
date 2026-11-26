---
name: delivery-workflow
description: 'Shared conventions of the ai-driven-dev-harness agents (challenger, architect, security-architect, performance-architect, builder, implementer, ui-ux-designer, reviewer): .ai/ artifacts, state.json phases, triage paths, language rule, project contract, skill precedence and the hook gates (state transitions, review gate, draft PR gate, push rules). Use when acting as one of these agents, or when a workflow gate blocks an action.'
user-invocable: false
---

# Delivery workflow conventions

The workflow turns a prompt, a spec or an Azure DevOps work item into a reviewed **draft** pull request in Azure Repos:

```
challenger ─▶ architect ─▶ builder ─▶ draft PR ─▶ user review in Azure DevOps ─▶ builder (PR feedback) ─▶ user publishes
 brief.md      plan.md      ├─ implementer subagent (one code lot at a time)
               │            ├─ ui-ux-designer subagent (one UI lot at a time)
               │            └─ reviewer subagent (independent, other model family)
               ├─ security-architect subagent (security.md, when the concern is flagged)
               └─ performance-architect subagent (performance.md, when the concern is flagged)
```

Interactive agents hand over with handoff buttons (`send: false`): the user validates the artifact, then sends the prefilled prompt.

## Artifacts

All workflow files live under `.ai/` at the repository root. They are excluded from git through `.git/info/exclude` and never committed.

| File | Written by | Purpose |
|---|---|---|
| `.ai/current` | challenger, close step | One line: the slug of the active work |
| `.ai/<slug>/state.json` | the agent of the current stage | Workflow state (below) |
| `.ai/<slug>/brief.md` | challenger | Validated business need |
| `.ai/<slug>/plan.md` | architect (builder on the fast path) | Implementation plan split into lots |
| `.ai/<slug>/security.md` | security-architect | Threats, mitigations, `SEC-n` requirements per lot, residual risk |
| `.ai/<slug>/performance.md` | performance-architect | Budgets, hot paths, measurement plan, `PERF-n` requirements per lot |
| `.ai/<slug>/review.md` | reviewer | Latest review: verdict, reviewed commit, findings |
| `.ai/<slug>/pr-description.md` | builder | Draft PR description (≤ 4000 characters) |
| `.ai/<slug>/feedback.md` | builder | Triage of the PR comments and the learnings proposed |
| `.ai/<slug>/.<subagent>-active` | hooks | Present while that subagent runs (reviewer, implementer, ui-ux-designer, security-architect, performance-architect) |
| `.ai/<slug>/.hooks.json` | hooks | Heartbeat, time of the user's last prompt, validation and escalation times, Stop block count |
| `.ai/<slug>/log.jsonl` | hooks | Append-only log of the hook decisions |
| `.ai/<slug>/usage.json` | hooks | Tokens per agent and model, runs and durations, read from the session transcript (cost table) |
| `.ai/archive/<slug>/` | close step | Closed workflows, kept for the learnings of later PRs |

No agent writes the hook-owned files. Since `.ai/` is not committed, the builder archives `brief.md` and `plan.md` on the draft PR as the **workflow record** thread (`azure-devops` skill).

Slug: kebab-case (`a-z`, `0-9`, single hyphens), at most 40 characters, prefixed with the work item ID when there is one (`1234-empty-borrowers-crash`); `archive` is reserved. The hooks ignore a `.ai/current` that breaks this rule. Start `state.json` from the [state template](./assets/state-template.json).

## state.json

Write it with the file edit tools only (a full write or an exact string replacement), never from the shell: the hooks simulate every edit and deny the ones that break the rules of [the gates](./references/gates.md).

| Field | Meaning | Set by |
|---|---|---|
| `slug` | Same value as `.ai/current`; never changes | challenger |
| `phase` | Current stage (below) | the agent of the stage |
| `path` | Triage result: `fast`, `standard` or `feature` | challenger |
| `base_branch` | Target branch of the PR (from the project contract); fixed once the build starts | challenger |
| `branch` | Always `ai/<slug>` | challenger |
| `work_item` | Azure DevOps work item ID, or `null` | challenger |
| `brief_validated` | `{"at": "<ISO date>", "head": "<HEAD sha>"}` once the user validated `brief.md` | challenger |
| `plan_validated` | Same, once the user validated `plan.md` | architect (builder on the fast path) |
| `lots_done` | Append-only list of `{"lot": <n>, "commit": "<sha>"}`, one per committed lot | builder |
| `pull_request` | Draft PR ID once created, or `null`; set once | builder |
| `record_thread` | ID of the workflow record thread on the draft PR, or `null`; set once | builder |
| `review_iterations` | Reviewer runs in the current build or feedback cycle, 2 at most | builder, before each reviewer run |
| `escalation` | `{"from": "<phase>", "reason": "..."}` while `escalated` | the agent that escalates |
| `language` | Language of the user's request (`fr`, `en`, ...) | challenger |
| `closed_at`, `closed_from`, `close_reason` | Written by the close step | close step |

Set a validation only after the user explicitly validated the file in a message, and do not edit the file afterwards: the hooks compare the time of the user's last prompt with the time the file was written.

### Phases

```
challenge ─▶ design ─▶ build ─▶ pr-open ─▶ triage ─▶ feedback ─▶ pr-open ─▶ (close) done
                  any active phase ─▶ escalated ─▶ challenge | design | build | triage | feedback | pr-open
```

| Phase | Who sets it | Leaves when |
|---|---|---|
| `challenge` | challenger, at the start | the brief is validated → `design` |
| `design` | challenger | the plan is validated → `build` (builder) |
| `build` | builder | the draft PR exists and HEAD is approved → `pr-open` |
| `pr-open` | builder | the user commented → `triage` (Address PR feedback) |
| `triage` | builder | the user validated `feedback.md` → `feedback`; nothing to change → `pr-open` |
| `feedback` | builder | the fixes are approved and pushed → `pr-open` |
| `escalated` | any agent, with `escalation.from` and `escalation.reason` | the user decided: the agent the user addresses moves to the phase the user chose; entering `build` or `feedback` resets `review_iterations` to 0 |
| `done` | the close step only | — |

Escalate whenever you stop for a decision you cannot make yourself (review limit reached, plan deviation, a hook denial you cannot fix), explain why, and wait for the user's answer.

### Close step

Once the user completed or abandoned the PR (or abandons the workflow), close it with `python <plugin>/scripts/close_workflow.py --repo . --reason "<why>"` (`python3` on Linux and macOS; `<plugin>` is the folder two levels above this skill). The hook asks the user to confirm. The script sets `phase: done`, moves `.ai/<slug>/` to `.ai/archive/<slug>/` and removes `.ai/current`. Nobody edits `state.json` by hand to close a workflow.

Its JSON output carries `usage_table`: the cost of each agent (tokens and estimated GitHub AI credits) as a Markdown table followed by its notes. Show it to the user as is, table and notes, without recomputing, rounding or completing any figure: `n/d` stays `n/d`. The same table is available at any time with `python <plugin>/scripts/usage_report.py --repo .` (add `--slug <slug>` for an archived workflow).

## Triage paths

| Path | When | Route |
|---|---|---|
| `fast` | Local, low-risk change: a few lines, no API, schema, security or dependency impact, obvious acceptance criteria | challenger → builder (single-lot plan) |
| `standard` | Usual change touching a few modules | challenger → architect → builder |
| `feature` | New capability, cross-cutting change, new dependency, data, schema, API or security impact | challenger → architect (several options, ADR) → builder |

When in doubt, choose the heavier path and say why.

## Language

Reply to the user and write the `.ai/` artifacts in the language of the user's request (`state.language`). Code, identifiers, code comments, commit messages and PR titles follow the project conventions (default: English).

## Project contract

Before working, read the project's agent instructions: `AGENTS.md`, `.github/copilot-instructions.md`, and the `*.instructions.md` files whose `applyTo` matches the files you touch. The `AI delivery workflow` section of `AGENTS.md` gives the build, test and lint commands, the mutation testing settings (`mutation-testing` skill), the base branch, the Azure DevOps organization, project and repository, the architecture docs folder, the domain glossary and an optional skill map. If this section is missing, tell the user and suggest the `project-onboarding` skill before going further.

## Architecture docs

The project's architecture map (`docs/architecture/` by default, or the folder named in the project contract) is committed with the code, unlike `.ai/`. The architect starts from it, the plan lists its **Documentation impact**, the implementer updates it in the same PR, and the reviewer checks it. Conventions: `architecture-mapping` skill.

## Skill precedence

1. Skills mapped to your stage in the project contract.
2. Other project skills (`.github/skills`, `.agents/skills`, `.claude/skills`) whose description matches the change.
3. This plugin's baseline checklists, only for topics no project skill covers.

When a project skill and a plugin skill disagree, the project skill wins. List the skills you applied in your artifact.

## Gates enforced by hooks

The hooks act only while a workflow is active (`.ai/current` present, `phase` not `done`). Their rules are listed once, in [the gates reference](./references/gates.md): protected files, phase transitions, roles, Stop gates, shell commands, Azure DevOps tools and the decision log. Read it when a hook denies or asks.

A denial is not an obstacle to work around: read its reason, fix the precondition, or escalate to the user.
