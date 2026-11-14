---
title: 0009 — The plugin is renamed ai-driven-dev-harness
status: accepted
date: 2026-11-14
supersedes: none
---
# 0009 — The plugin is renamed ai-driven-dev-harness

## Context
The name `ai-delivery-workflow` described the first version: one spec-to-draft-PR workflow. The plugin is now a harness around the coding agents: agents, skills, deterministic hooks, workflow state, architecture map and review gates. It runs today on GitHub Copilot in VS Code, and the owner wants it to become independent of the provider and usable with every model family. The repository is also expected to move from Azure DevOps to GitHub, where it will be created under the new name.

## Decision
The plugin is named `ai-driven-dev-harness` (`plugin.json`, documentation, hook log prefix, onboarding comments). New names and identifiers do not mention a provider or a model family.

Kept as they are, so that installed projects keep working: the `.ai/` working folder and its files, the `delivery-workflow` skill (it still describes the delivery workflow inside the harness), the "AI delivery workflow" section of `AGENTS.md` read by the agents, the agent names, and the `com.github.copilot/` folder required by the current host. The Azure DevOps URLs of this repository stay until the migration.

## Consequences
- Existing installs must replace the plugin: the client namespaces agents with the plugin name (`ai-driven-dev-harness:reviewer`); the hooks match agent names with or without a namespace (`is_agent_name`), so they are not affected.
- Any user setting, prompt or script that names `ai-delivery-workflow` (for example `chat.pluginLocations`) must be updated.
- Branches opened before the rename can reintroduce the old name; the rename is applied last and can be regenerated mechanically.

## Alternatives considered
- Keep `ai-delivery-workflow` — understates what the plugin has become and ties the name to one workflow.
- A name that mentions Copilot — contradicts the goal of a provider-independent harness.
- Rename the `delivery-workflow` skill and the `AGENTS.md` section too — breaks the contract of onboarded projects for no functional gain; can be done later with a compatibility period.
