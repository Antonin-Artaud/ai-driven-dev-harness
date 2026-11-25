---
title: 0010 — Independent lots run in parallel, each in a git worktree nested in .ai/
status: accepted
date: 2026-11-25
supersedes: none
---
# 0010 — Independent lots run in parallel, each in a git worktree nested in .ai/

## Context
Up to 0.5.0 the builder runs one implementer per lot, one after the other, in the single checkout of the work branch `ai/<slug>` (`skills/plan-execution/SKILL.md`). A plan of five lots waits for five runs even when most lots touch unrelated files. Two subagents cannot share one checkout: they would edit the same working tree, stage each other's files and commit each other's work. The host can run several subagents at once, and the usage reader already allowed for it (`scripts/hooks/usage.py`).

The hooks assumed a single checkout and a single run per subagent: the workflow was found from the closest `.git` (`find_repo_root`), so a linked worktree had no `.ai/current` and no gate at all; push and commit checks ran git in the hook's folder, whatever the command's `cd` or `-C`; the subagent marker was one file per agent, removed by the first `SubagentStop`; `.hooks.json` and `usage.json` were rewritten without a lock.

## Decision
- **Opt-in per project.** The project contract (`AGENTS.md`) says `Parallel lots: up to <n>` (2 to 4); missing or `off` keeps one lot at a time. Only the project knows whether its tests can run twice at once and in a fresh checkout.
- **Dependencies in the plan.** Each lot has a `Depends on` line (`none` or lot numbers), written by the architect; lots that change a common file are chained (`skills/solution-design/SKILL.md`). A plan without these lines runs sequentially.
- **One worktree per lot, nested in the workflow folder:** `.ai/<slug>/lot-<n>/` on the local branch `ai/<slug>--lot-<n>` (`--` never appears in a slug). `.ai/` is already excluded from git (the nested worktrees never show in the main checkout's status), the builder runs the main checkout's tests only once the lot worktrees are removed, and the hooks find the workflow from a path inside a lot worktree by its location alone (`find_workflow_root`, `lot_location` in `scripts/hooks/workflow_gate.py`), without running git. A worktree the user made elsewhere keeps its own root and no workflow.
- **Integration by rebase and fast-forward**, in plan order: `git -C <worktree> rebase ai/<slug>`, then `git merge --ff-only` in the main checkout, `git worktree remove` and `git branch -d`. The work branch keeps one commit per lot and a linear history; a conflict is resolved inside the lot worktree by an implementer run, never half-merged in the main checkout. The builder then runs the tests on the integrated branch, and the reviewer reviews `<merge-base>..HEAD` as before.
- **Hooks for concurrent runs:**
  - git commands are checked in the checkout they run in (`cd`, `pushd`, `Set-Location` on the same line, `git -C`); a commit in a folder the hook cannot resolve asks in `build` and `feedback` (`scripts/hooks/pre_tool_use.py`);
  - the coding subagents never push, and while a lot worktree exists they neither write nor commit in the main checkout; lot worktree paths are code paths, except their `.git` link and an `.ai/` folder inside them (`scripts/hooks/state_policy.py`);
  - `git worktree add` outside the convention asks the user;
  - a subagent marker holds one line per running instance (`add_marker_run`, `remove_marker_run`); the hooks take a short lock (`.ai/<slug>/.lock`, `locked`) before rewriting `.hooks.json`, `usage.json` or a marker;
  - the Stop hook does not let the main agent end a `build` or `feedback` turn while a lot worktree exists (lot gate, `scripts/hooks/stop.py`);
  - the close step removes clean lot worktrees and the lot branches the work branch contains, and stops before any change when a lot worktree holds uncommitted work (`scripts/close_workflow.py`).

## Consequences
- Independent lots of a plan run at the same time; the review, the PR and `state.json` do not change (`lots_done` stays append-only, in plan order, with the integrated commit).
- Each worktree starts without dependencies, build outputs or untracked local files: the implementer runs the install command first, and projects whose tests need a `.env` or a shared database keep `Parallel lots: off`.
- Parallel lots cost as many model runs as sequential ones, at the same time; GitHub's rate limits and the user's credit budget apply per run.
- The hooks see the command text, not the terminal: a `cd` run by an earlier command in a shared terminal is invisible. The rules that matter fail closed: a coding subagent's commit that seems to land in the main checkout during a wave is denied, and coding subagents never push. The hooks cannot tell which lot an implementer run belongs to, so one implementer writing in another lot's worktree is not detected (`docs/architecture/security.md`, Known gaps).
- While a wave runs, the editor sees copies of the code under `.ai/` (search, language servers, file watchers) until the worktrees are removed.
- Windows paths get longer by `.ai/<slug>/lot-<n>/` (about 50 characters at most): deep dependency trees may need `core.longpaths`.

## Alternatives considered
- **Worktrees next to the repository** (`../<repo>-lot-2`) — outside the VS Code workspace every edit asks for confirmation, and the hooks would have to parse `.git` files to find the workflow, also in the user's own worktrees.
- **Separate clones** — slower, and the lots would have to be fetched back through a remote.
- **Merge commits or cherry-picks to integrate** — merge commits blur "one commit per lot" and resolve conflicts in the main checkout; cherry-picked lot branches are not merged by ancestry and need `git branch -D`, which the workflow does not use.
- **A worktree for every lot, sequential ones included** — every lot would pay the install step; a wave of one lot runs in the main checkout as before.
- **Track the running lots in `state.json`** — the worktrees and lot branches already say it (`git worktree list`), and a new field would need new transition rules.
