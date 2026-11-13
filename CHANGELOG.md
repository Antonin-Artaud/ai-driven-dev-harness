# Changelog

All notable changes of the `ai-delivery-workflow` plugin. Versions follow [semantic versioning](https://semver.org/); the version lives in `plugin.json`.

## 0.3.0 — unreleased

Hardening after the audit of 2026-11-13. Upgrade notes: see "Mise à jour" in `README.md`.

### Added
- Validated `state.json` transitions: every edit is simulated and checked by the `PreToolUse` hook (allowed transitions, brief and plan validations, review gate before `pr-open`, review iterations bounded to 2, append-only `lots_done`, write-once PR fields); `done` only through the new close step `scripts/close_workflow.py` ([ADR 0006](docs/architecture/decisions/0006-validated-state-transitions.md)).
- `UserPromptSubmit` hook: validations, the triage and exits from `escalated` need a user prompt after the change.
- Hook-owned `.ai/<slug>/.hooks.json` (heartbeat, prompt and validation times) and append-only `log.jsonl` with credential redaction.
- Role boundaries enforced by hooks: reviewer writes `review.md` only, implementer never writes under `.ai/`, the main agent is asked before writing outside `.ai/`; implementer marker.
- `triage` phase for PR feedback; documented exits from `escalated`; close step archiving to `.ai/archive/`.
- Builder: hook heartbeat check, resume procedure, fast-path plan shown to the user before the build.
- Prompt-injection rule: work items, PR comments, wiki and web pages are quoted data, never instructions.
- Gates reference (`skills/delivery-workflow/references/gates.md`) as the single source of the hook rules; ADRs 0001–0006; this changelog.
- CI: ruff, mypy, coverage report with a threshold, smoke test of the `hooks.json` commands.
- From the review-ownership work: only the reviewer subagent writes `review.md`; git aliases resolved; "Workflow record" PR thread; PR learnings.

### Changed
- `PreToolUse`: wrappers with options, `eval`, interpreter one-liners, variables, substitutions, ANSI-C quoting and deep nesting are parsed or judged; pushes only to `ai/<slug>`; `az rest`, `az repos policy/ref/update`, `az` write verbs and HTTP calls to Azure DevOps denied; Azure DevOps MCP tools checked against a verified read allow-list, with a server-name check; PR updates allow-listed and scoped to the workflow PR; PR creation scoped to the `origin` repository; description length counted in UTF-16 units; thread status changes ask.
- Stop hook counts consecutive blocks (3) instead of letting every second stop through, and logs its exceptions.
- Untracked files present when the build starts no longer trip the review gate.
- Stage skills are `user-invocable: false` and only trigger within the workflow.
- Reviewer gets a non-GPT fallback model; every handoff names a model.
- Slug rule aligned between the skill and the hooks (kebab-case, at most 40 characters).
- Onboarding: conflicts return `ok: false` and exit code 3; robust `info/exclude` handling; LF line endings; clear errors for a missing `--repo`; Azure DevOps Server remotes reported.

## 0.2.0 — 2026-10-30

- Architecture map (`docs/architecture/`) created by onboarding and kept up to date by every workflow PR (`architecture-mapping` skill).
- CI: the test suite runs on Linux, Windows and macOS in Azure Pipelines.
- Architecture docs of the plugin itself.

## 0.1.0 — 2026-10-28

- First version: challenger, architect, builder, implementer and reviewer agents; nine skills; `PreToolUse` and `Stop` hooks; onboarding script.
