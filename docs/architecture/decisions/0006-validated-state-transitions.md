---
title: 0006 — Validated state.json transitions and hook-owned state
status: accepted
date: 2026-11-13
supersedes: none
---
# 0006 — Validated state.json transitions and hook-owned state

## Context

The hooks trust `.ai/<slug>/state.json` (phase) and `review.md` (verdict). Up to 0.2.0 any agent could write them with the file edit tools: set `phase: done` (every hook off), `escalated` (Stop gate off), or forge an `APPROVED` review, and "validated" was a Markdown line the agent wrote itself (audit of 2026-11-13). The agents need to keep updating `state.json` as they move through the stages, and the challenger and the architect have no shell.

## Decision

- Agents keep writing `state.json` with the file edit tools, but the `PreToolUse` hook **simulates every edit** (full write, exact string replacement, `apply_patch`) and validates the resulting state against the current one: allowed transitions, gate preconditions (validations, `APPROVED` review of a clean HEAD, PR recorded), write-once fields, the review iteration counter and append-only `lots_done` (`scripts/hooks/state_policy.py`). Edits it cannot simulate, and shell writes, are denied.
- Facts an agent must not forge live in **hook-owned files** no agent may write: `.ai/<slug>/.hooks.json` (time of the user's last prompt from `UserPromptSubmit`, last write and validation time of `brief.md`, `plan.md`, `feedback.md`, escalation time, untracked files at build start, Stop block count, heartbeat) and `log.jsonl`.
- A validation, the triage, and every exit from `escalated` need a user prompt recorded after the artifact changed or the escalation started.
- `done` is reached only through the close step (`scripts/close_workflow.py`), run by the builder after the user confirms (the hook asks) or by the user.
- `review.md` is written by the reviewer only, with `iteration` equal to `review_iterations` (1 or 2).

## Consequences

- An agent can no longer turn the gates off by editing a file; it has to escalate with a reason and wait for the user.
- The agents must follow a stricter protocol: validate only after the user's message and without editing the file afterwards; increment `review_iterations` before each reviewer run; set related fields in one edit.
- The proof of validation is "the user sent a message after the change", not the content of the message. It relies on the host sending `UserPromptSubmit`; without it the check is skipped (security.md, Known gaps).
- More logic in the hooks, covered by `tests/test_state_policy.py`.

## Alternatives considered

- **Hook-owned phase only, changed by a CLI** (`workflow.py transition build`) — the challenger and the architect have no shell, and a CLI run by the agent proves nothing more than a checked edit.
- **Signing state.json with a secret** — no place to keep a secret the agent cannot read.
- **Deny every agent write to state.json** — the workflow needs the agents to record their progress.
- **PostToolUse to record the result of each write** — not needed: the simulated result is checked before the write, and the hook state is updated only when the call is not denied.
