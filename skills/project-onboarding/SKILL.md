---
name: project-onboarding
description: 'Onboard a repository to the ai-delivery-workflow: detect the Azure DevOps organization, project and repository from the git remote, create or merge .vscode/mcp.json (ado-read, ado-write), exclude .ai/ from git, and write the "AI delivery workflow" section of AGENTS.md (build, test and lint commands, base branch, glossary, skill map). Use when setting up the workflow in a new project, or when an agent reports a missing project contract.'
argument-hint: 'Optional: base branch name'
---

# Project onboarding

## Procedure

1. **Preview the deterministic setup.** From the repository root, run [onboard.py](./scripts/onboard.py) with its absolute path (resolve it from this file's folder): `python <path>/onboard.py --repo . --dry-run` (`python3` on Linux and macOS). It prints a JSON summary: the Azure DevOps coordinates parsed from `origin`, the base branch, the planned `.vscode/mcp.json` change and the `.git/info/exclude` entries. It never prints credentials.
2. **Review the summary with the user**, then run the script again without `--dry-run`. Options: `--base-branch <name>` overrides the detected base branch; `--force` replaces conflicting `ado-read` or `ado-write` definitions. When the action is `manual` (the existing `mcp.json` has comments or cannot be parsed), show the printed snippet and let the user merge it.
3. **Gather the project facts** (read-only): build, lint and test commands (README, package manifests, `Makefile`, `azure-pipelines.yml`, CI scripts), code conventions, where the domain knowledge lives (glossary, docs, wiki), and the existing skills (`.github/skills`, `.agents/skills`, `.claude/skills`) and instructions.
4. **Write the project contract.** Fill the [AGENTS.md section template](./assets/agents-md-section.md) and add it to `AGENTS.md`, creating the file if needed. `AGENTS.md` is usually tracked by git: show the change and ask before writing it.
5. **Commit the onboarding.** Commit `AGENTS.md`, and `.vscode/mcp.json` when it is tracked, on the base branch (for example `docs: add the AI delivery workflow contract`) or through the team's usual PR. The workflow starts from a clean working tree: uncommitted files would be carried onto the work branch and trip the review gate.
6. **Check the environment** and report what is missing:
   - VS Code settings: `chat.plugins.enabled`, `chat.pluginLocations` (path of this plugin), `chat.useHooks`; the workspace must be trusted.
   - Python on the PATH as `python` (Windows) or `python3` (Linux, macOS), for the hooks.
   - MCP: start `ado-read` and `ado-write` from the MCP servers view (Microsoft Entra sign-in), then list the project's repositories with an `ado-read` tool.
