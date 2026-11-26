## AI delivery workflow

<!-- Project contract read by the ai-driven-dev-harness agents. Keep it short and factual. -->

### Commands
| Purpose | Command |
|---|---|
| Install | `<command or n/a>` |
| Build | `<command or n/a>` |
| Lint | `<command or n/a>` |
| Test | `<command>` |

### Mutation testing
<!-- mutation-testing skill. Mode: gate (threshold enforced by the reviewer), report (never blocking) or off (give the reason). -->
- Mode: `<gate | report | off: reason>`
- Tool: `<Stryker.NET | StrykerJS | PIT | mutmut | Infection | cargo-mutants>`
- Command: `<command that mutates a list of files>` (run from `<folder>`)
- Report: `<path>` (`<mutation-testing-elements | pitest-xml | tool>`)
- Threshold: `<80>`% of the mutants on changed lines detected
- Not mutated: `<generated code, migrations... excluded in the tool configuration | none>`

### Repository
- Base branch: `<main>`
- Azure DevOps: organization `<org>`, project `<project>`, repository `<repository>`
- Work branches: `ai/<slug>`

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
