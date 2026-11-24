# ai-driven-dev-harness

Agent plugin ([Agent Plugins 1.0](https://agent-plugins.org/) format) for VS Code and GitHub Copilot. It turns a request (prompt, spec or Azure DevOps work item) into a reviewed **Azure Repos draft PR**. The flow challenges the business need, plans the architecture starting from the project's architecture map, implements the plan while keeping that map up to date, and ends with an independent review based on the project's skills.

```
challenger ─▶ architect ─▶ builder ─▶ draft PR ─▶ your review in Azure DevOps ─▶ builder (feedback) ─▶ you publish
 brief.md      plan.md      ├─ implementer (subagent, one code batch at a time)
               │            ├─ ui-ux-designer (subagent, one UI batch at a time)
               │            └─ reviewer (independent subagent, different model family)
               ├─ security-architect (subagent when security is at stake: security.md)
               └─ performance-architect (subagent when performance is at stake: performance.md)
```

Each step between interactive agents is a **handoff** (`send: false`): you validate the brief or the plan, then click.

## Contents

| Item | Role |
|---|---|
| `challenger` (agent) | Challenges the need, triages the request (fast, standard, feature) and produces `brief.md` |
| `architect` (agent) | Starts from the `docs/architecture/` map, checks it against the code, compares options, challenges your vision and produces `plan.md`, split into batches, with the impact on the docs |
| `security-architect` (agent and architect subagent) | Models threats (STRIDE) and writes `security.md`: mitigations, `SEC-n` requirements per batch, residual risk. Does not code. Consulted by the architect when the brief or the change touches security, or started directly by you to analyse a plan |
| `performance-architect` (agent and architect subagent) | Sets budgets, finds hot paths and volumes, plans measurements and writes `performance.md` with `PERF-n` requirements per batch. Does not code. Consulted the same way |
| `builder` (agent) | Orchestrates the implementer, ui-ux-designer and reviewer, pushes the branch, opens the draft PR and handles PR comments |
| `implementer` (hidden subagent) | Implements one batch with TDD (red-green-refactor): tests, code, architecture doc update, one commit |
| `ui-ux-designer` (hidden subagent) | Implements the batches marked `Kind: ui`: the project's design system first, WCAG 2.1 AA accessibility, every state (loading, empty, error…), responsive, i18n, visual evidence when the project can produce it |
| `reviewer` (hidden subagent) | Reviews `merge-base..HEAD` applying the project's skills first, checks the plan's `SEC-n` and `PERF-n` requirements, the UI checklist for UI batches and the architecture docs, then writes `review.md` |
| `skills/` | `delivery-workflow`, `business-challenge`, `solution-design`, `security-design`, `performance-design`, `dotnet-performance`, `plan-execution`, `red-green-refactor`, `ui-ux-design`, `code-review`, `pr-feedback`, `azure-devops`, `project-onboarding`, `architecture-mapping` |
| `com.github.copilot/hooks/hooks.json` | Deterministic `UserPromptSubmit`, `PreToolUse`, `SubagentStart`, `SubagentStop` and `Stop` guardrails (Python scripts, standard library only) |

### .NET projects

On a .NET project, the `dotnet-performance` skill aims for the most memory-efficient and fastest code possible, on two levels. **Level A** applies to all .NET code written: no-tracking EF Core reads (`AsNoTracking` or `QueryTrackingBehavior.NoTracking` by default), projections, no N+1, keyset pagination, `ExecuteUpdate`/`ExecuteDelete`, async all the way, source-generated logging and JSON, CA18xx analyzers. **Level B** applies to hot paths covered by a `PERF-n` requirement: `Span<T>`, `Memory<T>`, `stackalloc`, `ArrayPool<T>`, `ValueTask`, `SearchValues`, Pipelines, SIMD… with a before/after BenchmarkDotNet benchmark (`[MemoryDiagnoser]`). Each rule cites its Microsoft Learn source and the required version. Onboarding adds the **`ms-learn`** MCP server (Microsoft Learn documentation, no authentication) so the agents check APIs against the official documentation.

The agents stay thin. The whole method lives in the skills, a portable format, and each project stays in control through its own skills: **the project's skills take precedence over the plugin's**.

## Prerequisites

- VS Code with GitHub Copilot, **Local** harness (for handoffs).
- Python ≥ 3.9 on the PATH: `python` on Windows, `python3` on Linux and macOS.
- Git, a repository hosted on Azure Repos and an Azure DevOps organization connected to Microsoft Entra ID (required by the remote MCP server).

## Installation

Source: [Antonin-Artaud / ai-driven-dev-harness](https://github.com/Antonin-Artaud/ai-driven-dev-harness) (GitHub).

**Option 1 (recommended while the plugin is being tuned): local clone.** Clone the repository, then declare it in the VS Code user settings (`settings.json`). Changes to the plugin are then picked up without reinstalling.

```powershell
git clone "https://github.com/Antonin-Artaud/ai-driven-dev-harness.git" <plugins-folder>\ai-driven-dev-harness
```

```jsonc
{
  "chat.plugins.enabled": true,
  "chat.pluginLocations": {
    "<plugins-folder>/ai-driven-dev-harness": true
  },
  "chat.useHooks": true
}
```

**Option 2: install from source.** Run **Chat: Install Plugin From Source** and paste the repository URL. VS Code clones the repository with your git credentials.

Replace `<plugins-folder>` with the folder of your choice (for example `C:/Users/<you>/source`).

In both cases the workspace must be trusted, otherwise the hooks do not run.

## Onboarding a project

1. Open the project and run the `/project-onboarding` skill.
2. The agent runs `skills/project-onboarding/scripts/onboard.py`, first with `--dry-run`:
   - it infers the organization, project and repository from the `origin` remote;
   - it creates or completes `.vscode/mcp.json` with `ado-read` (read only) and `ado-write` (draft PR and comments only);
   - it adds `.ai/` to `.git/info/exclude`, without touching the team's `.gitignore`;
   - with `--docs`, it creates the architecture map skeleton in `docs/architecture/` (or `--docs-path <folder>`), without overwriting existing files.
3. It offers to map the application (`architecture-mapping` skill): it shows you the pages and the "To confirm" items, then commits them on a dedicated branch for a PR.
4. It drafts the **AI delivery workflow** section of `AGENTS.md`: commands, base branch, glossary and an optional mapping between steps and the project's skills. It asks for your approval before writing.
5. Commit `AGENTS.md`, and `.vscode/mcp.json` if git tracks it, on the base branch. The builder requires a clean working tree before creating its `ai/<slug>` branch.
6. Start `ado-read` and `ado-write` from the MCP view (Entra sign-in), plus `ms-learn` on a .NET project (detected by a `*.sln`, `*.slnx`, `*.csproj` or `global.json`, or forced with `--dotnet`).

## Usage

1. Select the **challenger** agent and give your request, or a work item ID or URL.
2. Answer the questions (at most 5 per turn, each with a default answer) and validate `brief.md`. Then click **Design the solution**, or **Fast path** for a small change.
3. The **architect** proposes options, challenges your vision and produces `plan.md`. Validate it, then click **Implement the plan**. Depending on the brief (`Concerns` line), it consults the **security-architect** and the **performance-architect**, folds their requirements into the batches and marks the UI batches (`Kind: ui`), which then go to the **ui-ux-designer**.
4. The **builder** has the batches implemented and the branch reviewed (at most 2 review iterations, otherwise it hands back to you). It pushes the branch, then creates the draft PR linked to the work item; you confirm each of these two actions. It then archives the brief and the plan on the PR in the **🤖 Workflow record** thread.
5. Review the draft PR in Azure DevOps and comment.
6. Back in VS Code, click **Address PR feedback**. The builder enters the `triage` phase, classifies the comments and proposes **learnings**: the reusable rules your comments reveal, to add to the project's skills, its instructions or `AGENTS.md`. **You validate the classification and each learning**, then it fixes, commits the learnings separately (`docs(agents): …`), has the changes reviewed and replies to each thread. A comment made once does not have to be made again on the next PR.
7. Publish the PR yourself, then ask the builder to **close** the workflow (or run `python <plugin>/scripts/close_workflow.py --repo .`): `phase` becomes `done`, `.ai/<slug>/` is archived in `.ai/archive/` and `.ai/current` is removed. You confirm the closing. The builder then shows you the **cost per agent** (below).

## Cost per agent

When closing, the builder shows a table: for each agent (challenger, architect, builder and each subagent), the model, the number of runs, the duration, the tokens (input, cache read, cache write, output) and an **estimate in GitHub AI credits** (1 credit = $0.01), followed by the total. You can also show it at any time, including for an archived workflow:

```powershell
python <plugin>/scripts/usage_report.py --repo .                 # active workflow
python <plugin>/scripts/usage_report.py --repo . --slug <slug>   # archived workflow
python <plugin>/scripts/usage_report.py --repo . --json          # same summary as JSON
```

Where the numbers come from: neither VS Code nor Copilot exposes consumption to hooks, and GitHub does not break credits down per request. The hooks therefore read the session transcript (`transcript_path`) and attribute new requests to the agent that was running: to the subagent between its `SubagentStart` and its `SubagentStop`, otherwise to the phase's main agent. Everything is written to `.ai/<slug>/usage.json` (hooks only). Credits are computed with [GitHub](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing)'s public prices, copied into `scripts/hooks/pricing.json` (with the date they were taken in the file).

Limits:
- It is an **estimate**, not your bill: the exact count is in GitHub, *Billing > Metered usage*.
- The transcript format is not a stable VS Code API. If it has no token counters, the table says so and shows only runs and durations, with no made-up cost. Then run `usage_report.py --probe <transcript path>`: it lists the file's structure (the keys, never the values) so the reader can be adapted.
- A model missing from `pricing.json` (for example one you pick yourself that GitHub does not list) shows as `n/a` and the total becomes a minimum (`≥`). Every model named in the agents' headers, fallbacks included, has a row (a test checks it).
- GPT-6.2 Sol and GPT-6.2 Astra are not on GitHub's pricing page yet. GitHub bills them at OpenAI's list price, so their rows copy [OpenAI's prices](https://developers.openai.com/api/docs/pricing) until GitHub publishes its own.
- Subagents started in parallel share the transcript: their split is approximate.

## Architecture map (`docs/architecture/`)

Unlike `.ai/`, the architecture map is committed with the code. The folder is configurable in the **AI delivery workflow** section of `AGENTS.md` (`docs/architecture/` by default).

| Page | Content |
|---|---|
| `README.md` | Index, "To confirm" items |
| `context.md`, `containers.md` | C4 levels 1 and 2 |
| `components.md` | Modules, layers, allowed dependencies |
| `integrations.md` | External APIs and sequence diagrams of the critical flows |
| `data.md`, `security.md`, `quality.md` | Data, security, qualities (performance, reliability, observability) |
| `glossary.md` | Business glossary |
| `decisions/` | Numbered ADRs |

Rules: every statement cites the code file it comes from, anything not proven is marked "To confirm", diagrams are in Mermaid, and no secret or internal URL appears.

Lifecycle: the architect reads the map and looks at what changed since each page's last commit; the plan lists the **impact on the docs** (or `none` with the reason, for example a wording change); the implementer updates the docs in the same PR; the reviewer flags as `major` any change to an integration, flow, security rule, storage or component without a docs update. Outside a workflow, `architecture-mapping --refresh` catches up on drift. No hook checks the docs: that is the reviewer's job.

## Guardrails (hooks)

The hooks only act in a repository where a workflow is active (`.ai/current` present, `phase` other than `done`). The complete, up-to-date list of rules is in [the guardrails reference](skills/delivery-workflow/references/gates.md); in short:

| Rule | Behaviour |
|---|---|
| Workflow state | Every change to `state.json` is simulated then checked: allowed transitions, brief and plan validated by a message from you after their last change, review `APPROVED` before `pr-open`, at most 2 review iterations, leaving `escalated` only after your answer. `done` is reached only through the closing step. |
| Roles | Only the reviewer writes `review.md` (and nothing else); the implementer never writes under `.ai/`; the main agent asks for your confirmation before writing outside `.ai/`. The hooks' own files (`.hooks.json`, `log.jsonl`, markers) are never written by an agent. |
| End-of-turn checks (`Stop`) | In `build` and `feedback`, no end of turn with uncommitted or unreviewed code (`APPROVED` for HEAD); in `pr-open`, not before the **🤖 Workflow record** thread exists. At most 3 consecutive blocks. |
| Commit without tests | In the `build` or `feedback` phase, a `git commit` that changes code without any test file (`red-green-refactor` skill) asks for **your confirmation**: only you accept a batch without tests, for example on a legacy project with no unit or E2E tests. |
| Push | `git push` asks for confirmation and only targets `ai/<slug>`; force push, deletion, `--mirror`, `--all` and any other destination are refused, including through aliases, `sudo`, `env`, `timeout`, `xargs`, `eval`, `python -c` and variables. |
| Azure DevOps | Read MCP tools allowed (checked list); draft PR creation checked then confirmed; updates limited to the title and description of the workflow's PR; comments prefixed with `🤖`; everything else is refused. `az rest`, `az` writes and direct HTTP calls to Azure DevOps are refused. |
| Log | Every decision is appended to `.ai/<slug>/log.jsonl` (secrets masked). |

## Working files (`.ai/`, never committed)

| File | Content |
|---|---|
| `.ai/current` | Active slug |
| `.ai/<slug>/state.json` | Phase, track, branches, work item, brief and plan validations, completed batches, PR, record thread, review iterations, escalation, language |
| `.ai/<slug>/brief.md`, `plan.md` | Validated need, plan split into batches |
| `.ai/<slug>/review.md` | Latest review, with `verdict`, `reviewed_sha`, `base_sha` and `iteration` in the header |
| `.ai/<slug>/pr-description.md`, `feedback.md` | Draft PR description, comment classification and learnings |
| `.ai/<slug>/.hooks.json`, `log.jsonl` | Written by the hooks only: heartbeat, time of your last message, decision log |
| `.ai/<slug>/usage.json` | Written by the hooks only: tokens per agent and per model, runs, durations (see "Cost per agent") |
| `.ai/<slug>/.reviewer-active`, `.implementer-active` | Markers written by the hooks while a subagent runs |
| `.ai/archive/<slug>/` | Closed workflows |

These files stay local: the validated brief and plan outlive the PR thanks to the **🤖 Workflow record** thread, updated with a reply when the plan changes.

## Models

| Agent | Model (with fallback) |
|---|---|
| challenger, architect, security-architect, performance-architect | Claude Opus 5.5 (Claude Opus 5) |
| builder, implementer, ui-ux-designer | Claude Sonnet 5.5 (Claude Sonnet 5) |
| reviewer | GPT-6.2 Sol (GPT-6 Astra, then Gemini 4 Argon): a different family from the implementer and the ui-ux-designer, so fewer shared blind spots. The Gemini name, taken from GitHub's pricing page, is **to be confirmed** in your model picker. |

GPT-6.2 Sol is offered on the Copilot Pro+, Max, Business and Enterprise plans ([GitHub changelog](https://github.blog/changelog/2026-11-17-openais-gpt-6-2-astra-and-gpt-6-2-sol-now-available/)); on other plans, or when a Business or Enterprise administrator turns it off in the model policy, the reviewer uses its fallback.

In the Local harness, the `model` field of an agent's header applies to subagents. For interactive agents, the handoff's `model` (present on every handoff, including **Address PR feedback**) picks the model at handoff time, and the challenger uses the model selected in the picker. Names must exactly match those of the model picker, in the `<name> (copilot)` format.

## Portability to the Copilot harness

- The `handoffs` field is ignored: just switch agents by hand; the `.ai/` files carry the context from one step to the next.
- The hooks are declared with PascalCase event names and the `bash` and `powershell` keys, recognized by both harnesses. They read both input formats (`tool_name`/`tool_input` and `toolName`/`toolArgs`) and write their decisions in both output formats.
- No hook is declared in the agents' headers. The Copilot harness currently ignores those hooks for plugin-provided agents; here they are all at plugin level.

## Upgrading

1. Finish or close running workflows before changing versions: a `state.json` written by an earlier version may not satisfy the new transition rules.
2. Local clone: `git pull` in the plugin folder, then reload the VS Code window. Installed from source: reinstall the plugin.
3. Read the [CHANGELOG](CHANGELOG.md). Going from 0.2.0 to 0.3.0: brief and plan validations are now `state.json` fields (`brief_validated`, `plan_validated`), closing goes through `scripts/close_workflow.py`, and a new `UserPromptSubmit` hook is declared.
4. From `ai-delivery-workflow` (before the rename): the plugin is now called `ai-driven-dev-harness`. Uninstall the old plugin or remove its entry from `chat.pluginLocations`, then install the new one. The `.ai/` folders, the `delivery-workflow` skill and the "AI delivery workflow" section of `AGENTS.md` do not change: projects already onboarded have nothing to redo.
5. Check that the version shown in `.ai/<slug>/.hooks.json` (`heartbeat.version`) is the new one.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| The builder refuses to build: heartbeat missing or stale | The hooks are not running: enable `chat.useHooks`, trust the workspace, check `python`/`python3` on the PATH, then send a message and retry. |
| `state.json`: "not an allowed transition" or "wait for their validation" | The hook protects the steps: validate the brief or the plan explicitly in a message, without the agent changing the file afterwards. If stuck, ask for an escalation, then state the phase you want. |
| The main agent asks for confirmation for every file | Expected outside `escalated`: the main agent does not code. If it happens while the implementer is running, the host sends neither `agent_type` nor `agentName` (see "Things to check on first run"). |
| A `git push` is refused | The destination is not `ai/<slug>`, a force or delete option is present, or the upstream branch points elsewhere (`git branch --unset-upstream`). |
| A PR thread does not change status | Every status change asks for your confirmation; the record thread never changes status. |
| The cost table shows `n/a` everywhere | The VS Code transcript has no recognized token counters: run `usage_report.py --probe <transcript>` (the path is in `usage.json`, key `transcripts`) and open an issue with its output. |
| Understanding a hook decision | Read `.ai/<slug>/log.jsonl`: one line per decision, with the reason, the HEAD and the phase. |
| Workflow finished but the hooks still act | Close it: `python <plugin>/scripts/close_workflow.py --repo .` |
| `onboard.py` exits with code 3 | `ado-read` or `ado-write` already exist with a different definition: compare, then rerun with `--force`. |

## Tests

```powershell
cd tests
python -m unittest
```

The GitHub Actions CI (`.github/workflows/ci.yml`) runs these tests on Ubuntu (Python 3.9 and 3.12), Windows and macOS (Python 3.12) on every push to `main` and on every pull request, plus a quality job: `ruff`, `mypy` and script coverage with a minimum threshold.

Covered by the tests: hook decisions (Local and Copilot payloads), bypass corpus (`tests/test_bypass_corpus.py`), `state.json` transitions, closing, log, running the `hooks.json` commands in a real shell, git aliases, `review.md` ownership and the reviewer marker, review and record checks on real temporary git repositories, the onboarding script (including the architecture map skeleton), consistency of skills, agents and hooks.

## Things to check on first run

- The VS Code docs call the Local harness hooks "legacy". They work, but the editor is moving towards the Copilot harness.
- Open the Agent Debug Log to check the actual tool names (terminal, file editing, `ado-*` MCP tools). The hooks recognize Azure DevOps tools by name, on a server whose name contains `ado`, `azure`, `devops` or `vsts` (or without a prefix); they simulate file edits made with `create_file`, `replace_string_in_file`, `multi_replace_string_in_file` and `apply_patch`, and refuse other editing tools on `state.json`.
- If a handoff or a model is not found, adjust the name in the agent's header.
- Check in the Agent Debug Log that `SubagentStart` does receive `agentName: reviewer` (and `implementer`), or that subagent tool calls carry `agent_type`. Otherwise, writing `review.md` is refused to the reviewer itself, and every implementer write asks for your confirmation.
- Check that `UserPromptSubmit` is received: after your first message in an active workflow, `.ai/<slug>/.hooks.json` must contain `user_prompt_at`. Without it, the "you answered after the change" checks are skipped.

## Guardrail limits

The hooks protect against an agent's mistakes and drift, not against deliberate circumvention: a script written to disk and then run, a `GIT_CONFIG_*` variable or an Azure DevOps MCP server registered under an unexpected name can get through. Without an active workflow, no rule applies. Human review of the draft PR remains the final check. The remaining limits are listed in [docs/architecture/security.md](docs/architecture/security.md#known-gaps).

## License

No license has been chosen yet: it is the repository owner's decision (open item).
