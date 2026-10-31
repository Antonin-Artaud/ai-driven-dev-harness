---
title: Quality
verified_on: 2026-10-31
sources:
  - scripts/hooks/
  - com.github.copilot/hooks/hooks.json
  - azure-pipelines.yml
  - tests/
---
# Quality

The limits and reliability mechanisms present in the code. No performance target is stated.

## Limits

| Limit | Value | Source |
|---|---|---|
| Hook timeout | 15 s | `com.github.copilot/hooks/hooks.json` |
| Git call timeout in a hook | 10 s | `git` in `scripts/hooks/workflow_gate.py` |
| PR description | 4000 characters, Markdown included | `PR_DESCRIPTION_LIMIT` in `scripts/hooks/workflow_gate.py` |
| Review iterations per cycle | 2, then `phase: escalated` | `skills/plan-execution/SKILL.md` |
| Challenger questions per round | 5 | `com.github.copilot/agents/challenger.agent.md` |
| Lot size | about 300 changed lines | `skills/solution-design/SKILL.md` |
| Python | 3.9 minimum | `README.md`, `azure-pipelines.yml` |

## Reliability

- **Hooks never trap the agent**: `stop.py` lets the stop through on any exception and after a first block (`stop_hook_active`); on an exception, `pre_tool_use.py` only denies PR and comment writes (`scripts/hooks/stop.py`, `scripts/hooks/pre_tool_use.py`).
- **One script for two hosts**: VS Code Local (snake_case) and Copilot (camelCase) inputs are accepted, and every decision is written in both formats (`parse_input`, `pre_tool_use_result`, `stop_result` in `scripts/hooks/workflow_gate.py`).
- **Robust file reading** for files written on Windows (BOM, UTF-16, cp1252) (`read_text`).
- Git runs with `GIT_OPTIONAL_LOCKS=0` so the hooks do not interfere with other git processes (`workflow_gate.py`).

## Observability

No logs or metrics: every denial carries the `[ai-delivery-workflow]` prefix and a reason readable by the agent and the user (`LOG_PREFIX` in `scripts/hooks/workflow_gate.py`).

## Tests and CI

- `python -m unittest` in `tests/`: 69 tests on 2026-10-31 (hooks, onboarding, plugin structure).
- Azure Pipelines runs the suite on Ubuntu (Python 3.9 and 3.12), Windows and macOS (Python 3.12) on every push to `main` (`azure-pipelines.yml`). Azure Repos ignores the pipeline's `pr` key, so the pipeline is set as a build validation policy on `main` to run on pull requests (confirmed by the project owner; the policy lives in Azure DevOps, not in the code).
