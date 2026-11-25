# Changelog

All notable changes of the `ai-driven-dev-harness` plugin. Versions follow [semantic versioning](https://semver.org/); the version lives in `plugin.json`.

## Unreleased — parallel lots in git worktrees

Design: [ADR 0010](docs/architecture/decisions/0010-parallel-lots-in-git-worktrees.md).

### Added
- Independent lots run in parallel, opt-in per project: `Parallel lots: up to <n>` (2 to 4) in the "AI delivery workflow" section of `AGENTS.md`; missing or `off` keeps one lot at a time. The onboarding template and procedure ask the question (fresh checkout after the install command, no shared database, port or file between two test runs).
- Plan: each lot has a `Depends on` line (`none` or lot numbers); lots that change a common file are chained (`solution-design` skill, plan template).
- Builder (`plan-execution` skill): waves of independent lots, one git worktree per lot in `.ai/<slug>/lot-<n>/` on the local branch `ai/<slug>--lot-<n>`, parallel implementer runs, integration in plan order by `git rebase` then `git merge --ff-only`, conflicts resolved in the lot worktree, tests on the integrated branch, then the review as before; resume picks up leftover lot worktrees. Implementer: lot worktree rules (absolute paths, `git -C`, install first, never the main checkout). Reviewer: checks how lots built in parallel fit together.
- Hooks:
  - the workflow is found from inside a lot worktree (`find_workflow_root`); worktrees elsewhere keep no workflow;
  - git pushes and commits are checked in the checkout they run in (`cd`, `pushd`, `Set-Location`, `git -C`); a commit in a folder the hook cannot resolve asks in `build` and `feedback`;
  - the implementer and the ui-ux-designer never push, and while a lot worktree exists they neither write nor commit in the main checkout; lot worktrees are code paths for them (not their `.git` link or an `.ai/` inside);
  - `git worktree add` outside the lot convention asks the user;
  - lot gate: the Stop hook keeps the main agent in a `build` or `feedback` turn while a lot worktree is left;
  - subagent markers hold one line per running instance, and `.hooks.json`, `usage.json` and the markers are rewritten under a short lock (`.ai/<slug>/.lock`, hook-owned).
- Close step: removes clean lot worktrees and the lot branches the work branch contains, keeps and reports the others, and stops before any change when a lot worktree holds uncommitted work.
- `tests/test_worktrees.py`.

### Fixed
- A `.` or `..` segment in a path (`.ai/<slug>/x/../state.json`) hid a protected workflow file from the file edit checks and from the shell write check: paths are normalized first.

## Unreleased — reviewer on GPT-6.2 Sol

### Changed
- The reviewer runs on **GPT-6.2 Sol** instead of GPT-6.1 Sol, at the same rates. Its first fallback (GPT-6 Astra) does not change; its Gemini fallback becomes **Gemini 4 Argon**, as Gemini 3.1 Pro is no longer on GitHub's pricing page. GitHub reports that GPT-6.2 Sol catches nearly twice as many real issues in code review as GPT-6.1 Sol ([changelog](https://github.blog/changelog/2026-11-17-openais-gpt-6-2-astra-and-gpt-6-2-sol-now-available/)). It is offered on the Copilot Pro+, Max, Business and Enterprise plans; elsewhere the reviewer uses its fallback. The other agents stay on Claude Opus 5.5 and Claude Sonnet 5.5.

### Added
- `scripts/hooks/pricing.json`: GPT-6.2 Sol ($2 input, $0.10 cached input, $2.50 cache write, $10 output per 1M tokens) and GPT-6.2 Astra ($8, $0.40, $10, $40), with the long-context tier above 272K prompt tokens. GitHub's page does not list them yet and GitHub bills them at OpenAI's list price, so these rows copy OpenAI's prices. The other rates are unchanged, checked on 2026-11-24.
- Tests: every model named in an agent's header, fallbacks included, has a row in `pricing.json`, and each handoff names the first model of the agent it opens.

## Unreleased — moved to GitHub

### Changed
- The repository moved from Azure Repos to GitHub: `plugin.json` `repository`, the install source and the `git clone` of the README point to <https://github.com/Antonin-Artaud/ai-driven-dev-harness>.
- CI: GitHub Actions (`.github/workflows/ci.yml`) replaces `azure-pipelines.yml`, with the same jobs: tests on Ubuntu (Python 3.9 and 3.12), Windows and macOS, then ruff, mypy and coverage (minimum 80%). It also runs on pull requests.
- `README.md` is now in English, like the rest of the documentation.

### Fixed
- `usage.py`: `summarize` narrows the `agents` and `models` entries in a way mypy accepts (3 errors with a recent mypy).

## Unreleased — renamed to ai-driven-dev-harness

Design: [ADR 0009](docs/architecture/decisions/0009-rename-ai-driven-dev-harness.md).

### Changed
- **Breaking for existing installs:** the plugin is renamed from `ai-delivery-workflow` to `ai-driven-dev-harness` (`plugin.json` `name`). The agents are now namespaced `ai-driven-dev-harness:<agent>` by the client, and the hook messages carry the `[ai-driven-dev-harness]` prefix. Uninstall the old plugin (or remove its entry from `chat.pluginLocations`) and install the new one; finish or close running workflows first.
- Unchanged on purpose: the `.ai/` working folder and its files, the `delivery-workflow` skill, the "AI delivery workflow" section of `AGENTS.md` (projects already onboarded keep working), the agent names and the Azure DevOps coordinates of this repository until it moves.

## 0.5.0 — unreleased

Red-green-refactor (PR 10), on top of 0.4.0 (specialist agents).

### Added
- `red-green-refactor` skill: the builder requires the test-first cycle in every implementer prompt and checks the `TDD cycle` evidence of each lot report; the implementer applies it (failing test, minimal code, refactor).
- Test-first gate: in the `build` and `feedback` phases, `PreToolUse` asks the user before a `git commit` that changes code without any test file, so only the user accepts a lot without tests.

## Unreleased — cost per agent

### Added
- Cost table at the end of a workflow: the close step prints `usage_table`, one row per agent (model, runs, duration, input, cache read, cache write and output tokens, estimated GitHub AI credits) and the total; the builder shows it to the user. `scripts/usage_report.py` prints it at any time, for an active or archived workflow, in Markdown or JSON, and `--probe` lists the key structure of a transcript.
- Hook-owned `.ai/<slug>/usage.json`: the `Stop`, `SubagentStart` and `SubagentStop` hooks read the session transcript (`transcript_path` / `transcriptPath`) and attribute each new model request to the agent that ran; requests are deduplicated by id. No figure is invented: without token counts in the transcript, only runs and durations are shown.
- `scripts/hooks/pricing.json`: published GitHub Copilot rates per model (USD per 1M tokens, long-context tiers, 1 AI credit = $0.01), checked on 2026-11-14.

## 0.4.0 — unreleased

Depends on 0.3.0 (audit hardening). Design: [ADR 0007](docs/architecture/decisions/0007-specialist-agents.md).

### Added
- `ui-ux-designer` builder subagent and `ui-ux-design` skill: lots marked `Kind: ui` in the plan, design system first, WCAG 2.1 AA, every state, responsive, i18n, visual evidence.
- `security-architect` and `performance-architect` agents (architect subagents, also user-invocable) with the `security-design` and `performance-design` skills; they write `security.md` and `performance.md` with `SEC-n` and `PERF-n` requirements per lot, integrated into `plan.md` by the architect when the brief's `Concerns` line or the change calls for them.
- Brief template: `Concerns` line and UX intent; plan template: UX intent, specialists consulted, `Kind` and security/performance requirements per lot.
- Review: the reviewer checks `SEC-n` and `PERF-n` with the plan's severity, and a UI section of the baseline checklist on UI lots.
- `dotnet-performance` skill (.NET projects only, [ADR 0008](docs/architecture/decisions/0008-stack-specific-performance-skills.md)): Tier A defaults for all .NET code and Tier B hot-path techniques under a `PERF-n`, each rule with its pitfalls, version and Microsoft Learn source; BenchmarkDotNet evidence; `.NET performance` line in the lot report and section in the review checklist.
- Onboarding adds the read-only Microsoft Learn MCP server (`ms-learn`, `https://learn.microsoft.com/api/mcp`) on .NET projects (or with `--dotnet`); the architect, performance-architect, implementer, ui-ux-designer and reviewer get its tools.
- Hooks: markers and role rules for the three new subagents (designer has the implementer's rights; each specialist writes only its own file; other subagents may not write those files; no shell writes to them).

### Changed
- Security and performance checklists moved from `solution-design` to the new skills.

## 0.3.1 — unreleased

### Fixed (Windows)
- Subagent markers whose file time is slightly ahead of `time.time()` (coarse Windows clock) were treated as stale, so the reviewer could be denied `review.md`; a 5 s clock skew is now tolerated (`marker_active`, heartbeat).
- `state.json` edits on a file saved with CRLF line endings were not simulated when the edit used LF (exact replacement or patch), so legitimate edits were denied; matching now ignores the line ending.
- Workflow paths are matched case-insensitively (`.AI\\Slug\\STATE.JSON`), as on Windows file systems.
- Tests read `plugin.json` as UTF-8 explicitly; new `tests/test_windows_inputs.py` exercises Windows-style inputs on every OS.

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
