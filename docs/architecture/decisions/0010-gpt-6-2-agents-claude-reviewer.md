---
title: 0010 — Agents on OpenAI GPT-6.2 Sol, the reviewer on Claude
status: accepted
date: 2026-11-24
supersedes: 0004
---
# 0010 — Agents on OpenAI GPT-6.2 Sol, the reviewer on Claude

## Context
The owner wants the workflow agents to run on OpenAI's GPT-6.2 models, generally available in GitHub Copilot since 2026-11-17 ([GitHub changelog](https://github.blog/changelog/2026-11-17-openais-gpt-6-2-astra-and-gpt-6-2-sol-now-available/)): GPT-6.2 Astra, OpenAI's most capable model, and GPT-6.2 Sol, its everyday coding and code review model, at a quarter of Astra's per-token price ([OpenAI](https://openai.com/index/introducing-gpt-6-2-astra-sol/)).

The plugin runs in VS Code through Copilot, which serves OpenAI models: an agent picks its model by its model picker name in the `model` field of its header, and each handoff names the model of the agent it opens (`README.md`, section "Models"). No proxy or other runtime is needed.

[ADR 0004](./0004-cross-family-reviewer.md) put the implementer on Claude and the reviewer on GPT. Moving the implementer to GPT would leave the reviewer in the same family. GPT-6.2 is offered on the Copilot Pro+, Max, Business and Enterprise plans only, and GitHub's pricing page does not list it yet.

## Decision
- Every agent but the reviewer runs on GPT-6.2 Sol, falling back to GPT-6.1 Sol: the challenger, the architect, the security-architect, the performance-architect, the builder, the implementer and the ui-ux-designer.
- The rule of 0004 is carried forward: the reviewer runs on another model family than the implementer and the ui-ux-designer, now Claude Opus 5.5, then Claude Opus 5, then Gemini 4 Argon. It is a subagent that does not see the implementation conversation, writes only `review.md`, and the hooks trust only its verdict.
- Each handoff names the first model of the agent it opens. `scripts/hooks/pricing.json` has a row for every model the agents name, fallbacks included, and for GPT-6.2 Astra, which a user can still pick for an interactive agent. The GPT-6.2 rows copy OpenAI's list price, which GitHub says it bills, until GitHub's page lists them.
- `tests/test_plugin_structure.py` checks the cross-family rule, the handoff models and the pricing rows.

## Consequences
- Below 272K prompt tokens per request, the four design agents cost half what they cost on Claude Opus 5.5 ($2 input and $10 output per 1M tokens, against $4 and $20), the three build agents cost the same as on Claude Sonnet 5.5, and the reviewer costs twice what it cost on GPT-6.1 Sol. Above 272K, GPT-6.2 requests use OpenAI's long-context rates. The cost table applies these rates.
- The design agents and the build agents now share one model: there is no stronger tier for the challenge, the design and the threat model.
- Independent coding tests published at the time put Claude Opus 5.5 ahead of GPT-6.2 Sol on agentic coding, while OpenAI's own figures show them close. The review findings and the PR feedback are where a quality drop would show; the learnings go to the skills.
- On a plan without GPT-6.2, or when a Business or Enterprise administrator turns it off, the agents use their fallback. The reviewer still needs Claude or Gemini in the plan: two vendors stay required, as in 0004.
- The GPT-6.2 rows of `pricing.json` must be replaced with GitHub's once its page lists them.
- The agents and skills do not depend on a model family ([ADR 0001](./0001-method-in-skills.md)), so no prompt changes.

## Alternatives considered
- GPT-6.2 Astra for the four design agents, the tier Claude Opus held — twice the per-token price of Claude Opus 5.5 and four times that of GPT-6.2 Sol, for a gain the published coding comparisons do not show clearly.
- Only the reviewer on GPT-6.2 Sol — the smallest change, but the other agents stay on Claude, against the owner's request.
- Model profiles chosen by configuration, with a script that rewrites the agent headers — closer to the provider-independent goal of [ADR 0009](./0009-rename-ai-driven-dev-harness.md), but the host reads static headers, so the script would modify tracked files of the installed plugin; deferred.
- Keep a GPT reviewer — breaks the cross-family rule once the implementer runs on GPT.
