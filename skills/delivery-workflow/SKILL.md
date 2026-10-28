---
name: delivery-workflow
description: 'Shared conventions of the ai-delivery-workflow agents (challenger, architect, builder, implementer, reviewer): .ai/ artifacts, state.json phases, triage paths, language rule, project contract, skill precedence and the hook gates (review gate, draft PR gate, push confirmation). Use when acting as one of these agents, or when a workflow gate blocks an action.'
user-invocable: false
---

# Delivery workflow conventions

The workflow turns a prompt, a spec or an Azure DevOps work item into a reviewed **draft** pull request in Azure Repos:

```
challenger ─▶ architect ─▶ builder ─▶ draft PR ─▶ user review in Azure DevOps ─▶ builder (PR feedback) ─▶ user publishes
 brief.md      plan.md      ├─ implementer subagent (one lot at a time)
                            └─ reviewer subagent (independent, other model family)
```

Interactive agents hand over with handoff buttons (`send: false`): the user validates the artifact, then sends the prefilled prompt.

## Artifacts

All workflow files live under `.ai/` at the repository root. They are excluded from git through `.git/info/exclude` and never committed.

| File | Written by | Purpose |
|---|---|---|
| `.ai/current` | challenger | One line: the slug of the active work |
| `.ai/<slug>/state.json` | every agent | Workflow state (below) |
| `.ai/<slug>/brief.md` | challenger | Validated business need |
| `.ai/<slug>/plan.md` | architect (builder on the fast path) | Implementation plan split into lots |
| `.ai/<slug>/review.md` | reviewer | Latest review: verdict, reviewed commit, findings |
| `.ai/<slug>/pr-description.md` | builder | Draft PR description (≤ 4000 characters) |
| `.ai/<slug>/feedback.md` | builder | Triage of the PR comments |

Slug: kebab-case, at most 40 characters, prefixed with the work item ID when there is one (`1234-empty-borrowers-crash`). Start `state.json` from the [state template](./assets/state-template.json).

## state.json

| Field | Meaning |
|---|---|
| `slug` | Same value as `.ai/current` |
| `phase` | `challenge` → `design` → `build` → `pr-open` ⇄ `feedback` → `done`; `escalated` when the user must decide |
| `path` | Triage result: `fast`, `standard` or `feature` |
| `base_branch` | Target branch of the PR (from the project contract) |
| `branch` | Work branch: `ai/<slug>` |
| `work_item` | Azure DevOps work item ID, or `null` |
| `pull_request` | Draft PR ID once created, or `null` |
| `review_iterations` | Reviewer runs in the current build or feedback cycle |
| `language` | Language of the user's request (`fr`, `en`, ...) |

Set `phase` when you enter your stage. Set `escalated` whenever you stop for a decision you cannot make yourself, and explain why. The user, or the builder on request, sets `done` once the PR is completed or abandoned.

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

Before working, read the project's agent instructions: `AGENTS.md`, `.github/copilot-instructions.md`, and the `*.instructions.md` files whose `applyTo` matches the files you touch. The `AI delivery workflow` section of `AGENTS.md` gives the build, test and lint commands, the base branch, the Azure DevOps organization, project and repository, the architecture docs folder, the domain glossary and an optional skill map. If this section is missing, tell the user and suggest the `project-onboarding` skill before going further.

## Architecture docs

The project's architecture map (`docs/architecture/` by default, or the folder named in the project contract) is committed with the code, unlike `.ai/`. The architect starts from it, the plan lists its **Documentation impact**, the implementer updates it in the same PR, and the reviewer checks it. Conventions: `architecture-mapping` skill.

## Skill precedence

1. Skills mapped to your stage in the project contract.
2. Other project skills (`.github/skills`, `.agents/skills`, `.claude/skills`) whose description matches the change.
3. This plugin's baseline checklists, only for topics no project skill covers.

When a project skill and a plugin skill disagree, the project skill wins. List the skills you applied in your artifact.

## Gates enforced by hooks

The plugin hooks only act in a repository with an active workflow (`.ai/current` present, `phase` not `done`):

- **Review gate (Stop):** in the `build` and `feedback` phases, the main agent cannot finish while there are uncommitted changes, or while `review.md` is missing, stale (`reviewed_sha` ≠ HEAD) or not `APPROVED`. Escalate (`phase: escalated`) to stop legitimately.
- **Draft PR gate:** `repo_pull_request_write` `create` requires `phase: build`, `isDraft: true`, a clean tree, an `APPROVED` review of HEAD, HEAD pushed to `origin/<branch>`, the current branch as source, `base_branch` as target and a description of at most 4000 characters; then the user confirms. Autocomplete, policy bypass, publishing (`isDraft: false`), abandoning, voting and reviewer changes are denied.
- **Push:** `git push` asks the user; force pushes, deletions and mirror pushes are denied.
- **Azure DevOps writes:** only draft PR creation or update and PR comments are allowed; work items are never modified; workflow comments must start with `🤖`.
- **az CLI:** `az repos pr` writes, `az boards work-item` writes and write calls through `az devops invoke` are denied. Azure DevOps is accessed through the MCP servers only.

A denial is not an obstacle to work around: read its reason, fix the precondition, or escalate to the user.
