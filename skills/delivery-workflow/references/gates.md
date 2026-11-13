# Workflow gates enforced by the hooks

This page is the single source for the hook rules. The README, the architecture docs and the other skills link here.

The hooks (`com.github.copilot/hooks/hooks.json`, scripts in `scripts/hooks/`) only act in a repository with an active workflow: `.ai/current` names a slug whose `state.json` phase is not `done`. A denial is not an obstacle to work around: read its reason, fix the precondition, or escalate to the user.

## Files the hooks protect

| File | Who writes it | How |
|---|---|---|
| `.ai/<slug>/state.json` | the agent of the current stage | file edit tools only (full write, exact string replacement or patch); every edit is simulated and checked (below) |
| `.ai/<slug>/review.md` | the reviewer subagent only | file edit tools; `iteration` must equal `review_iterations` (1 or 2) |
| `.ai/current` | challenger, close step | cannot switch away while the workflow is in `build`, `pr-open`, `triage` or `feedback` |
| `.ai/<slug>/.hooks.json`, `log.jsonl`, `.reviewer-active`, `.implementer-active` | the hooks only | never written by an agent |

None of these files is ever written from the shell (`>`, `Set-Content`, `cp`, `sed -i`, `python -c` ...).

## Phase transitions (state.json)

| From | Allowed to | Condition checked by the hook |
|---|---|---|
| (new file) | `challenge` | — |
| `challenge` | `design`, `escalated` | `design`: `brief_validated` set |
| `design` | `challenge`, `build`, `escalated` | `build`: `brief_validated` and `plan_validated` set, neither file changed since its validation; `review_iterations: 0` |
| `build` | `pr-open`, `escalated` | `pr-open`: `pull_request` set and an `APPROVED` review of a clean HEAD |
| `pr-open` | `triage`, `escalated` | — |
| `triage` | `feedback`, `pr-open`, `escalated` | `feedback`: `feedback.md` exists and the user wrote after it; `review_iterations: 0` |
| `feedback` | `pr-open`, `escalated` | `APPROVED` review of a clean HEAD |
| `escalated` | `challenge`, `design`, `build`, `triage`, `feedback`, `pr-open` | the user wrote after the escalation, plus the condition of the target phase; entering `build` or `feedback` resets `review_iterations` to 0 |
| any | `done` | never through an edit: only the close step (`scripts/close_workflow.py`), which the user confirms |

Other rules on every edit:

- `slug` and `branch` (`ai/<slug>`) never change; `pull_request` and `record_thread` are set once; `base_branch` only changes before the build.
- `brief_validated` and `plan_validated` are `{"at": "<ISO date>", "head": "<HEAD sha>"}` and need a user message after the last write of `brief.md` or `plan.md`. Do not edit the file after the user validates it: the validation would be stale.
- `review_iterations` grows by one per reviewer run, never decreases within a cycle and never exceeds 2: once two reviews still request changes, escalate.
- `lots_done` is append-only within a build cycle.
- Escalating needs `"escalation": {"from": "<current phase>", "reason": "<why the user must decide>"}`.

"The user wrote after" is checked against the time of the user's last prompt, recorded by the `UserPromptSubmit` hook. If the host never sends that event, these checks cannot be verified and are skipped (see the Known gaps of `docs/architecture/security.md`).

## Roles

| Caller | Rule |
|---|---|
| reviewer subagent | writes `review.md` only; any other file write is denied |
| implementer subagent | never writes under `.ai/` |
| main agent (challenger, architect, builder) | writing outside `.ai/` asks the user in every phase except `escalated` |

The caller is recognized by the `agent_type` field of hooks fired in a subagent, or by the `.reviewer-active` and `.implementer-active` markers written by `SubagentStart` and removed by `SubagentStop` and `Stop`. The hooks cannot tell the challenger, the architect and the builder apart: the main-agent rule is enforced by phase.

## Stop gates

- **Review gate:** in `build` and `feedback`, the main agent cannot finish while there are uncommitted changes (untracked files that existed when the build started excepted), or while `review.md` is missing, stale (`reviewed_sha` ≠ HEAD) or not `APPROVED`. After 2 iterations the message asks to escalate.
- **Record gate:** in `pr-open`, once the draft PR exists, the main agent cannot finish until `record_thread` is set.
- The Stop hook blocks at most 3 times in a row, then lets the stop through and logs it. A user prompt or an allowed stop resets the count.

## Shell commands

| Command | Decision |
|---|---|
| `git push` to `ai/<slug>` (no refspec on the work branch, `ai/<slug>`, `HEAD`, `HEAD:refs/heads/ai/<slug>`) | ask |
| force, `--force-with-lease`, `--mirror`, `--delete`, `--prune`, `--all`, `+` or `:` refspecs | deny |
| any other destination (`main`, `ai/x:main`, `HEAD:refs/heads/main`, tags), or an upstream that is not `ai/<slug>` | deny |
| a push with variables or substitutions (`$BRANCH`, `$g push`, `` `git` push ``) | ask, or deny when a force option is visible (`$'-f'`) |
| `eval`, `python -c`, `node -e`, `perl -e`, `ruby -e`, `php -r`, or shells nested deeper than 2 levels, mentioning git, az or Azure DevOps | ask, or deny for a force push |
| the close step (`close_workflow.py`) | ask |
| `az rest`, `az repos policy`, `az repos pr` writes, `az boards work-item` writes, `az devops invoke` writes, any `az devops/repos/boards/pipelines/artifacts` write verb (`create`, `update`, `delete`, `run` ...) | deny |
| other `az devops/repos/boards/pipelines/artifacts` commands that are not `list` or `show` | ask |
| `curl`, `wget`, `Invoke-RestMethod`, `Invoke-WebRequest` to `dev.azure.com` or `*.visualstudio.com` | deny |

The parser follows `;`, `&&`, `|`, subshells, wrappers and their options (`sudo -u`, `env -i`, `env -S`, `timeout`, `nice`, `xargs`, `find -exec`, `nohup`, `time`), launchers (`bash -c`, `cmd /c`, `pwsh -Command`, `iex`, `eval`), simple variables assigned on the same line (`g=git; $g push`), and git aliases (`-c alias.*`, `git config alias.*` on the same line, the git config, `!` shell aliases).

## Azure DevOps MCP tools

Tools are recognized by name (`repo_*`, `wit_*`, `wiki*`, `pipelines_*`, `testplan*`, `work*`, `core_*`, `search_*`, `advsec_*`, `enterprise_live_migration*`) on a server whose prefix names Azure DevOps (`ado`, `azure`, `devops`, `vsts`) or without prefix. Known read tools pass; every other tool of these servers is treated as a write and denied, except:

| Tool and action | Decision |
|---|---|
| `repo_pull_request_write` `create` | the draft PR gate (`azure-devops` skill): phase `build`, no PR yet, `isDraft: true`, no autocomplete or bypass, description ≤ 4000 UTF-16 units, repository and project of `origin`, clean tree, `APPROVED` review of HEAD, current branch `ai/<slug>` as source, `base_branch` as target, HEAD pushed; then ask, showing repository, project, source and target |
| `repo_pull_request_write` `update` | only `title`, `description`, `isDraft: true` on `state.pull_request`; anything else denied |
| `repo_pull_request_write` `vote`, `update_reviewers` | deny |
| `repo_pull_request_thread_write` `create`, `reply`, `update` | content starts with `🤖`, on `state.pull_request` |
| `repo_pull_request_thread_write` `update_status` | ask (the hook cannot tell who opened the thread); denied on the workflow record thread |

## Observability

Every decision (deny, ask), Stop block or release, subagent start and stop, close, hook error and web tool call is appended to `.ai/<slug>/log.jsonl` with the time, hook, tool, decision, reason, HEAD and phase. URLs with credentials and token arguments are redacted. The hooks refresh a heartbeat (time and plugin version) in `.ai/<slug>/.hooks.json`, at most once a minute.
