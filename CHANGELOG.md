# Changelog

All notable changes of the `ai-driven-dev-harness` plugin. Versions follow [semantic versioning](https://semver.org/); the version lives in `plugin.json`.

## 0.7.0 — unreleased — multi-repository projects

Design: [ADR 0011](docs/architecture/decisions/0011-workflow-root-above-the-repositories.md).

### Added
- **`.ai/` one level above the repositories.** For a project that spans several git repositories, `.ai/` may sit in the folder that holds them (the workspace opened in VS Code). The hooks, `close_workflow.py` and `usage_report.py` look for `.ai/current` from the working folder up to the folder that holds its repository, never higher (`find_workflow_root`); a repository's own `.ai/current` still wins.
- `state.json` `repositories`: the folders of the repositories the workflow changes, each with an optional `base_branch` and its own write-once `pull_request` and `record_thread`. Folders sit directly in the workflow root, must be git repositories when the build starts, and are fixed from then on. Unlisted repositories of the workspace are not governed. Empty for a single repository, which behaves as before.
- Per-repository gates: the work branch `ai/<slug>` in each repository; push and test-first commit rules checked in the repository the command runs in (`cd`, `pushd`, `popd`, `Set-Location`, `git -C` and aliases followed; a command whose repository cannot be told asks); untracked baseline per repository; the decision log records the HEAD of each repository.
- One review for all the repositories: `reviewed_sha: api=<sha> web=<sha>` names the HEAD of each repository with changes; the Stop review gate, the `pr-open` gate and the draft PR gate check every repository.
- One draft PR per repository with changes: `repositoryId` is matched to a listed repository by its Azure Repos name, the checks (branch, base branch, push, existing PR) apply to that repository, `pr-open` needs a PR for every repository with changes, and the record gate a record thread on each PR. PR updates and comments are scoped to the workflow's PRs.
- `onboard.py --workspace <folder>`: `.vscode/mcp.json` in the workspace, `.ai/` excluded in each repository, and in the repository that holds the workspace when there is one (`workspace_git_exclude`).
- Skills and templates: multi-repository sections in delivery-workflow, the gates reference, plan-execution, azure-devops, code-review, pr-feedback, solution-design (`Repository:` per lot), business-challenge and project-onboarding (workspace `AGENTS.md` with a `Repositories` table); `repositories` in the state template.
- Tests: `tests/test_multi_repo.py` (workspace with real repositories and bare origins).

## 0.6.0 — unreleased — mutation testing

Design: [ADR 0010](docs/architecture/decisions/0010-mutation-testing-of-changed-code.md).

### Added
- `mutation-testing` skill, loaded by the builder, the implementer, the ui-ux-designer and the reviewer: once a lot is green, the implementer mutates the files it changed, kills the surviving mutants with behavior tests (the mutant is the red step) and disables only equivalent mutants in the code, with a reason. The gate is the **mutation score of the changed lines** against the threshold of the project contract (80% by default); mutants on unchanged lines are reported, never blocking. The reviewer reruns it on the branch: in `gate` mode a score below the threshold, an unjustified disable comment or a changed file left out of the run is a major finding; a survivor in code that enforces a `SEC-n` requirement takes its severity.
- `skills/mutation-testing/scripts/mutation_gate.py` (standard library): reads a mutation-testing-elements JSON report (StrykerJS, Stryker.NET, Stryker4s) or a PIT `mutations.xml`, keeps the mutants on the lines changed since the merge base (untracked files included), computes the score, lists survivors, disabled mutants and changed code files missing from the report, and refuses a report whose source differs from the working tree. Exit codes 0 passed, 2 below the threshold, 1 unusable report. Checked against real StrykerJS 10.1 and PIT 1.20 reports.
- Tools reference (Stryker.NET, StrykerJS, PIT, mutmut, Infection, cargo-mutants): install, run on changed files, report, in-code disable syntax and output folders, each with its sources; unverified points are marked "To confirm".
- Project contract: a **Mutation testing** part (mode `gate`, `report` or `off`, tool, command, report, threshold, code not mutated). Without it, mutation testing is off.
- `onboard.py` detects the stacks from their marker files, reports the matching tool in `mutation_testing` and adds its output folders to `.git/info/exclude`, so a run does not trip the review gate's clean tree check; `--mutation-tool <tool>` (repeatable) or `none` overrides the detection.
- Lot report `Mutation testing` entry, plan header line, review template and PR description lines; red-green-refactor, solution-design (testing strategy), code-review (baseline checklist) and delivery-workflow point to the new skill.
- Tests: `tests/test_mutation_gate.py`, onboarding detection, wiring and sourced tools reference in `tests/test_plugin_structure.py`.

### Changed
- The reviewer may run the project's mutation testing command and the gate script, and leaves the working tree as it found it.
- This repository's contract sets mutation testing `off`, with the reason.

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
