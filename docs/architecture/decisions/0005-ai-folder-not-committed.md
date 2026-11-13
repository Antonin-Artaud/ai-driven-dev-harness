---
title: 0005 — The .ai/ working folder is never committed
status: accepted
date: 2026-11-13
supersedes: none
---
# 0005 — The .ai/ working folder is never committed

Backfilled on 2026-11-13 from the design of 0.1.0 (`skills/delivery-workflow/SKILL.md`, `skills/project-onboarding/scripts/onboard.py`).

## Context
The workflow produces working files (brief, plan, review, state, PR description, feedback triage, and since 0.3.0 the hook state and log). They can quote work item content and are only useful while the work is in progress. Teams own their `.gitignore`.

## Decision
All working files live in `.ai/` at the repository root, excluded through `.git/info/exclude` (never the team's `.gitignore`). The brief and the plan survive the PR as the "🤖 Workflow record" thread on the draft PR. Closed workflows are kept locally under `.ai/archive/` (close step).

## Consequences
- No workflow noise in the history or the diff; the review gate ignores `.ai/`.
- The record on the PR is the durable trace; local archives can be deleted freely.
- The hooks must read and protect files that git does not track ([ADR 0006](./0006-validated-state-transitions.md)).

## Alternatives considered
- Committing `.ai/` on the work branch — pollutes the PR and leaks work item content into the repository.
- Storing the state in Azure DevOps — needs write access beyond the draft PR and comments.
