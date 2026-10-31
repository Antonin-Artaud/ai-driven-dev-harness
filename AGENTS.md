# AGENTS.md

## AI delivery workflow

<!-- Project contract read by the ai-delivery-workflow agents. Keep it short and factual. -->

### Commands
| Purpose | Command |
|---|---|
| Install | n/a (Python standard library only) |
| Build | n/a |
| Lint | n/a |
| Test | `python -m unittest -v` from `tests/` (`python3` on Linux and macOS) |

### Repository
- Base branch: `main`
- Azure DevOps: organization `<org>`, project `<project>`, repository `ai-delivery-workflow`
- Work branches: `ai/<slug>`

### Architecture docs
- Architecture docs: `docs/architecture` (kept up to date by every workflow PR; see the architecture-mapping skill)

### Domain
- Glossary and domain documentation: `docs/architecture/glossary.md`
- Key business rules: the hooks only act when a workflow is active; the user alone publishes, completes or abandons a PR, and accepts a code commit without tests; work items are never modified.

### Conventions
- Commit messages: Conventional Commits (`feat:`, `ci:`, `docs:`)
- Code style: Python ≥ 3.9, standard library only for the hooks and scripts
- Documentation language: English for `docs/architecture/`, skills, agents and code
