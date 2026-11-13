---
title: 0002 — Azure DevOps through the MCP servers only
status: accepted
date: 2026-11-13
supersedes: none
---
# 0002 — Azure DevOps through the MCP servers only

Backfilled on 2026-11-13 from the design of 0.1.0 (`skills/azure-devops/SKILL.md`, `skills/project-onboarding/scripts/onboard.py`).

## Context
The agents read work items, wiki pages and PR threads, and create a draft PR and comments, all with the user's identity. The az CLI and the REST API can do anything the user can, including completing PRs, changing policies or editing work items.

## Decision
Azure DevOps is accessed only through the remote Azure DevOps MCP server, declared twice by `onboard.py`: `ado-read` (`X-MCP-Readonly: true`, toolsets `repos,wit,wiki`) for every agent that reads, and `ado-write` (`X-MCP-Tools` limited to `repo_pull_request_write` and `repo_pull_request_thread_write`) for the builder only. The hooks deny `az` writes, `az rest` and HTTP calls to Azure DevOps, and check the two write tools (gates reference of the `delivery-workflow` skill).

## Consequences
- Two independent filters: the server filter (headers) and the hooks.
- Microsoft Entra ID sign-in is required; on-premises Azure DevOps Server is not served (onboarding reports it).
- If the MCP tools fail, the workflow degrades to manual steps (pasted work item, PR created by the user from `pr-description.md`).

## Alternatives considered
- az CLI with an allow-list of commands — too many write paths (`az rest`, `az devops invoke`) to check reliably.
- A personal access token in the project — a secret to store and rotate.
