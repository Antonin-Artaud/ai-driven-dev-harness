---
title: Quality
verified_on: 2026-11-13
sources:
  - scripts/hooks/
  - com.github.copilot/hooks/hooks.json
  - azure-pipelines.yml
  - ruff.toml
  - mypy.ini
  - .coveragerc
  - tests/
---
# Quality

The limits and reliability mechanisms present in the code. No performance target is stated.

## Limits

| Limit | Value | Source |
|---|---|---|
| Hook timeout | 15 s | `com.github.copilot/hooks/hooks.json` |
| Git call timeout in a hook | 4 s (`GIT_TIMEOUT`); at most 5 git calls for a PR creation | `git` in `scripts/hooks/workflow_gate.py` |
| PR description | 4000 UTF-16 units, Markdown included | `PR_DESCRIPTION_LIMIT` in `scripts/hooks/workflow_gate.py`, `utf16_length` in `pre_tool_use.py` |
| Review iterations per cycle | 2, then `phase: escalated`, enforced by the hooks | `MAX_REVIEW_ITERATIONS` in `scripts/hooks/workflow_gate.py` |
| Consecutive Stop blocks | 3, then the stop is let through and logged | `MAX_STOP_BLOCKS` in `scripts/hooks/workflow_gate.py` |
| Heartbeat | refreshed at most once a minute; stale after 10 minutes for the builder | `HEARTBEAT_INTERVAL`, `plan-execution` skill |
| Challenger questions per round | 5 | `com.github.copilot/agents/challenger.agent.md` |
| Lot size | about 300 changed lines | `skills/solution-design/SKILL.md` |
| Python | 3.9 minimum | `README.md`, `azure-pipelines.yml` |

## Reliability

- **Hooks never trap the agent**: `stop.py` lets the stop through on any exception and after 3 consecutive blocks; on an exception, `pre_tool_use.py` only denies Azure DevOps writes and protected workflow file writes (`scripts/hooks/stop.py`, `scripts/hooks/pre_tool_use.py`).
- **Atomic hook state**: `.hooks.json` is rewritten through a temporary file and `os.replace` (`update_hook_state`).
- **Cheap on every call**: the repository root and the workflow are found from the file system; git runs only for push, PR, transition and review checks (`find_repo_root`, `load_workflow`).
- **One script for two hosts**: VS Code Local (snake_case) and Copilot (camelCase) inputs are accepted, and every decision is written in both formats (`parse_input`, `pre_tool_use_result`, `stop_result` in `scripts/hooks/workflow_gate.py`).
- **Robust file reading** for files written on Windows (BOM, UTF-16, cp1252) (`read_text`).
- Git runs with `GIT_OPTIONAL_LOCKS=0` so the hooks do not interfere with other git processes (`workflow_gate.py`).

## Observability

Every denial carries the `[ai-driven-dev-harness]` prefix and a reason readable by the agent and the user (`LOG_PREFIX`). Every decision, Stop block or release, subagent start and stop, close, hook error and web tool call is appended to `.ai/<slug>/log.jsonl` with credentials redacted (`log_event`, `redact` in `scripts/hooks/workflow_gate.py`). The heartbeat in `.ai/<slug>/.hooks.json` shows that the hooks run and which plugin version runs them. No metrics.

## Tests and CI

- `python -m unittest` in `tests/`: hook decisions on real temporary git repositories, the table-driven bypass corpus (`tests/test_bypass_corpus.py`), `state.json` transitions (`tests/test_state_policy.py`), close step, log and heartbeat, a smoke test that runs every `hooks.json` command through a shell, the onboarding script and the plugin structure.
- Azure Pipelines runs the suite on Ubuntu (Python 3.9 and 3.12), Windows and macOS (Python 3.12) on every push to `main` (`azure-pipelines.yml`). A quality job runs `ruff check` and `ruff format --check` (`ruff.toml`), `mypy` (`mypy.ini`; mypy needs Python ≥ 3.10 to run, Python 3.9 compatibility is checked by the 3.9 test job) and the suite under `coverage` with a minimum of 80% on `scripts/` and `onboard.py`, hook subprocesses included (`.coveragerc`, `tests/sitecustomize.py`). Azure Repos ignores the pipeline's `pr` key, so the pipeline is set as a build validation policy on `main` to run on pull requests (confirmed by the project owner; the policy lives in Azure DevOps, not in the code).
