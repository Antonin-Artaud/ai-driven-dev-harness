---
title: Integrations
verified_on: 2026-11-13
sources:
  - skills/azure-devops/
  - skills/project-onboarding/scripts/onboard.py
  - scripts/hooks/
  - com.github.copilot/hooks/hooks.json
---
# Integrations

The external systems the plugin calls, then the critical flows.

| System | Purpose | Protocol | Authentication | Timeout, retry | Source |
|---|---|---|---|---|---|
| Azure DevOps MCP server `ado-read` | Work items, repos, wiki, read-only | MCP over HTTP, headers `X-MCP-Readonly: true` and `X-MCP-Toolsets: repos,wit,wiki` | Microsoft Entra ID, user's identity | Not handled by the plugin. On failure, the agent asks the user to paste the work item | `skills/project-onboarding/scripts/onboard.py`, `skills/azure-devops/SKILL.md` |
| Azure DevOps MCP server `ado-write` | `repo_pull_request_write` and `repo_pull_request_thread_write` only | MCP over HTTP, `X-MCP-Tools` header | Microsoft Entra ID, user's identity | Not handled. On failure, the builder hands `pr-description.md` to the user for a manual PR | same |
| Git (`origin` remote) | Work branch, push, working tree status, reviewed SHAs, Azure DevOps coordinates of `origin` | `git` CLI as a subprocess | User's git credentials | 4 s per call in the hooks, no retry; the repository root is found without git | `scripts/hooks/workflow_gate.py` |
| VS Code / Copilot host | Calls the hooks on `UserPromptSubmit`, `PreToolUse`, `SubagentStart`, `SubagentStop` and `Stop` | Subprocess, JSON on stdin/stdout | n/a | 15 s per hook | `com.github.copilot/hooks/hooks.json` |

The MCP server URL is built from the organization of the `origin` remote (`MCP_ENDPOINT` in `skills/project-onboarding/scripts/onboard.py`). The `az` CLI and direct HTTP calls are never used to write to Azure DevOps (`scripts/hooks/pre_tool_use.py`).

## Flow: draft PR creation

Source: `skills/plan-execution/SKILL.md`, `scripts/hooks/pre_tool_use.py` (`evaluate_pr_create`).

```mermaid
sequenceDiagram
  participant B as builder
  participant H as PreToolUse hook
  participant U as User
  participant G as git / origin
  participant A as ado-write
  B->>H: git push -u origin ai/<slug>
  H->>U: ask: confirm the push
  U-->>G: push
  B->>H: repo_pull_request_write create
  H->>H: phase build, no PR yet, isDraft, description ≤ 4000 UTF-16
  H->>G: repository of origin, clean tree, APPROVED review of HEAD, branch ai/<slug>, origin/ai/<slug> = HEAD
  alt a check fails
    H-->>B: deny + reason
  else all checks pass
    H->>U: ask: create the DRAFT PR?
    U-->>A: confirmation
    A-->>B: PR ID
  end
```

## Flow: review gate on stop

Source: `scripts/hooks/stop.py`, `scripts/hooks/workflow_gate.py` (`review_gate`).

```mermaid
sequenceDiagram
  participant V as VS Code
  participant S as stop.py
  participant G as git
  V->>S: Stop event (JSON)
  alt no workflow, or phase not build/feedback/pr-open
    S-->>V: {} (stop allowed)
  else 3 consecutive blocks already
    S-->>V: {} (released, logged)
  else
    S->>G: HEAD, git status, merge-base
    alt nothing implemented on the branch yet
      S-->>V: {}
    else uncommitted changes, or review missing, stale or not APPROVED
      S-->>V: decision block + reason
    else
      S-->>V: {}
    end
  end
```

Any exception in `stop.py` lets the agent stop and is logged. In `pre_tool_use.py`, an exception denies Azure DevOps write tools and writes mentioning protected workflow files, never other tools, and is logged (`main` in both scripts).
