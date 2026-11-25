## AI delivery workflow

<!-- Project contract read by the ai-driven-dev-harness agents. Keep it short and factual. -->

### Commands
| Purpose | Command |
|---|---|
| Install | `<command or n/a>` |
| Build | `<command or n/a>` |
| Lint | `<command or n/a>` |
| Test | `<command>` |

### Repository
- Base branch: `<main>`
- Azure DevOps: organization `<org>`, project `<project>`, repository `<repository>`
- Work branches: `ai/<slug>`
- Parallel lots: <off | up to N (2 to 4)> (independent lots of a plan run at the same time, each in its own git worktree; only when the install and test commands work in a fresh checkout without untracked local files, and two test runs at once share no database, port or file)

### Architecture docs
- Architecture docs: `<docs/architecture>` (kept up to date by every workflow PR; see the architecture-mapping skill)

### Domain
- Glossary and domain documentation: `<docs/architecture/glossary.md, or path or link>`
- Key business rules: <one line each, or a link>

### Skill map (optional)
| Stage | Skills to apply first |
|---|---|
| Challenge | `<project skill>` |
| Design | `<project skill>` |
| Review | `<project skill>` |

### Conventions
- Commit messages: `<convention>`
- Code style and linters: `<tools>`
