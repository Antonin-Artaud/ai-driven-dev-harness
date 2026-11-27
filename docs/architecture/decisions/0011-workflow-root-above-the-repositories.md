---
title: 0011 — The workflow root may sit one level above the repositories
status: accepted
date: 2026-11-27
supersedes: none
---
# 0011 — The workflow root may sit one level above the repositories

## Context
Until 0.6.0, `.ai/` lived at the root of the git repository ([ADR 0005](./0005-ai-folder-not-committed.md)), and every hook found the workflow with `find_repo_root`. The owner asked to allow it one level up, for projects that span several repositories: a change to an API and its front end is one need, one brief, one plan and one review, but two repositories, two work branches and two pull requests in Azure Repos (Azure Repos has no pull request across repositories). VS Code can be opened on the folder that holds such repositories side by side, and the agents then run from that folder. The gates must keep their meaning in every repository the workflow changes, and a single-repository project must behave exactly as before.

## Decision
- **Workflow root.** `.ai/` sits in the workflow root: the repository root, or the folder that holds the repositories (the **workspace**). The hooks and the scripts look for `.ai/current` from the working folder up to the folder that holds its git repository, never higher (`find_workflow_root` in `scripts/hooks/workflow_gate.py`); a `.ai/current` closer to the working folder wins, so a repository with its own workflow keeps it.
- **Listed repositories.** `state.json` gains `repositories`: the folders, directly in the workflow root, of the repositories the workflow changes, each with an optional `base_branch` and its own write-once `pull_request` and `record_thread`. It is set by the challenger, refined by the architect, and fixed once the build starts; each entry must then be the root of a git repository (`check_repositories`, `_repositories_gate` in `scripts/hooks/state_policy.py`). An empty list means a single repository at the workflow root, with the top-level fields as before. A repository of the workspace that is not listed is not governed by the workflow.
- **Per repository gates.** The work branch is `ai/<slug>` in every listed repository. The push and commit rules apply to the repository the command runs in: `PreToolUse` follows `cd`, `pushd`, `popd`, `Set-Location` and `git -C` within the command line; a command whose repository cannot be told asks the user. The untracked baseline is recorded per repository.
- **One review.** The reviewer reviews all the repositories together, and `reviewed_sha` names the HEAD of each repository with changes (`api=<sha> web=<sha>`). The review gate (Stop, `pr-open`, PR creation) requires every repository to be clean and each named HEAD to be the current one; a repository still at its merge base needs no entry.
- **One draft PR per repository with changes.** The draft PR gate maps `repositoryId` to a listed repository by its Azure Repos name (from `origin`), never by GUID, and applies its checks to that repository and its base branch. PR updates and comments are scoped to the workflow's PRs; the record gate requires a record thread on each.
- **Onboarding.** `onboard.py --workspace <folder>` writes `.vscode/mcp.json` in the workspace, excludes `.ai/` in each repository, and in the repository that holds the workspace when there is one. The workspace `AGENTS.md` lists the repositories.

## Consequences
- A change across repositories keeps one brief, one plan, one review loop and one cost table, and still ends in draft PRs the user publishes one by one.
- The hooks run a few more git calls per repository on the PR, review and Stop paths (`docs/architecture/quality.md`).
- The cwd tracking is approximate: a `cd` in an earlier terminal call, in a variable, a subshell or a pipe leaves the repository unknown, and the hook asks instead of checking (known gaps, `docs/architecture/security.md`).
- The folders and base branches cannot change once the build starts: a repository discovered late needs an escalation back to `design`.
- Only one level: a repository nested deeper, or a `.ai/` two levels up, is not supported.

## Alternatives considered
- **One workflow per repository**, each with its own `.ai/`: duplicates the brief, the plan and the review, and loses the review of the contract between the repositories.
- **Searching `.ai/` in every parent folder:** a stray `.ai/` in a home folder would govern every repository below it.
- **A single top-level `pull_request` for the first repository:** the other PRs would escape the scoping of updates and comments and the record gate.
- **Git submodules or a meta-repository:** imposes a repository layout on the team; the workspace may still be inside a git repository, which the onboarding handles.
- **`reviewed_sha` as a single combined hash:** opaque to the user and to the reviewer; per-repository pairs keep each HEAD readable.
