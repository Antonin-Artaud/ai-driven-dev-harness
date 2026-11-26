# AGENTS.md

## AI delivery workflow

<!-- Project contract read by the ai-driven-dev-harness agents. Keep it short and factual. -->

### Commands
| Purpose | Command |
|---|---|
| Install | n/a (Python standard library only) |
| Build | n/a |
| Lint | n/a |
| Test | `python -m unittest -v` from `tests/` (`python3` on Linux and macOS) |

### Mutation testing
- Mode: `off` — the hooks' suite runs real git repositories in subprocesses (about 25 s per run), too slow to replay per mutant; sizing a scoped run (for example mutmut on `scripts/hooks/`, POSIX only) is a follow-up

### Repository
- Base branch: `main`
- Hosting: GitHub, `Antonin-Artaud/ai-driven-dev-harness` (the workflow's Azure Repos draft PR step does not apply to this repository yet)
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
