---
title: 0003 — Hooks in Python, standard library only
status: accepted
date: 2026-11-13
supersedes: none
---
# 0003 — Hooks in Python, standard library only

Backfilled on 2026-11-13 from the design of 0.1.0 (`scripts/hooks/`, `com.github.copilot/hooks/hooks.json`).

## Context
The hooks run on every tool call of every agent, on Windows, macOS and Linux, from a plugin installed by cloning a repository. Nothing may need to be installed besides the plugin, and a hook must answer within its timeout (15 s).

## Decision
The hooks are Python scripts (Python ≥ 3.9, standard library only), declared with `bash` (`python3`) and `powershell` (`python`) commands. They share `workflow_gate.py`, read both the VS Code Local and the Copilot payload shapes, and write their decision in both output formats.

## Consequences
- No dependency to install or audit; the same scripts run on every platform (CI matrix in `.github/workflows/ci.yml`).
- Python must be on the PATH (onboarding checks it).
- Parsing (shell commands, JSON with comments, front matter) is written by hand and covered by tests, including a bypass corpus (`tests/test_bypass_corpus.py`).
- Linters and type checkers run in CI only; they are not runtime dependencies.

## Alternatives considered
- Node.js hooks — another runtime to require on every machine.
- PowerShell and bash scripts — two implementations to keep in sync.
- A compiled binary — distribution and signing per platform.
