---
title: 0004 — A reviewer from another model family
status: superseded
date: 2026-11-13
supersedes: none
---
# 0004 — A reviewer from another model family

Superseded by [0010](./0010-gpt-6-2-agents-claude-reviewer.md): the cross-family rule stands, the families changed (implementer on GPT, reviewer on Claude).

Backfilled on 2026-11-13 from the design of 0.1.0 (`com.github.copilot/agents/reviewer.agent.md`).

## Context
The implementer and the reviewer read the same brief and plan. A reviewer from the same model family tends to share the implementer's blind spots and to trust its style.

## Decision
The reviewer runs on another model family than the implementer: GPT first, with a Gemini fallback, while the implementer runs on Claude. It is a subagent that does not see the implementation conversation, writes only `review.md`, and the hooks trust only its verdict. `tests/test_plugin_structure.py` checks that its first model is from another family than the implementer's and that its fallbacks span two families.

## Consequences
- Fewer shared blind spots; disagreements surface as findings.
- Model display names are host-specific and must be checked in the model picker (`README.md`).
- Two vendors must be available in the user's Copilot plan.

## Alternatives considered
- Same model with a reviewer prompt — cheaper, but shares the blind spots.
- Several reviewers voting — slower and costlier for the size of a lot.
