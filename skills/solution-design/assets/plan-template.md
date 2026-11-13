# Plan — <title>

- Brief: `.ai/<slug>/brief.md` · Path: <fast | standard | feature>
- Base branch: `<base>` · Work branch: `ai/<slug>`
- Build / lint / test commands: `<from the project contract>`
- Stack: <e.g. .NET 9, C# 13, EF Core 9 — `dotnet-performance` Tier A; Tier B in scope: yes (PERF-n) | no> (or the stack of the project)

## Context
<Relevant existing modules, patterns and constraints, with file paths.>

- Architecture docs used: <pages read, their drift since their last commit, contradictions found — or "no architecture docs">

## UX intent
<Only when the change has a user-facing surface: users, tasks, key screens and their states (loading, empty, error, success), from the brief. Or: **none** — no user-facing change.>

## Specialists consulted
- Security: <`.ai/<slug>/security.md` (SEC-1…SEC-n integrated below) | not consulted: <reason>>
- Performance: <`.ai/<slug>/performance.md` (PERF-1…PERF-n integrated below) | not consulted: <reason>>

## Options
| Option | Summary | Fit with existing code | Complexity | Risk | Performance | Security | Reversibility |
|---|---|---|---|---|---|---|---|
| A — minimal change | … | … | … | … | … | … | … |
| B — … | … | … | … | … | … | … | … |

## Decision (ADR)
- **Context:** …
- **Decision:** …
- **Consequences:** …
- **Non-goals:** …

## Where I challenge your vision
- <Point of disagreement, evidence> — **Decision:** <the user's decision>

## Standards applied
- <project skill, instruction or plugin checklist> — <what it implies for this change>

## Lots
### Lot 1 — <title>
- **Kind:** <code | ui>
- **Goal:** …
- **Tasks:**
  1. `<path>` — <change> — done when <criterion>
- **Tests:** <new or updated tests, mapped to AC1, AC2…>
- **Security and performance requirements:** <SEC-n, PERF-n with their severity if missed | none>
- **Commit message:** `<type>(<scope>): <summary>`

### Lot 2 — <title>
- …

## Documentation impact
| Page or ADR | Change | Lot |
|---|---|---|
| `docs/architecture/integrations.md` | <add the X API row and its sequence diagram> | 2 |
| `docs/architecture/decisions/NNNN-<title>.md` | <new ADR from the decision above> | 2 |

Or: **none** — <reason: wording, labels, styles, tests only, internal refactoring...>

## Acceptance criteria coverage
| Criterion | Lot | Test |
|---|---|---|
| AC1 | 1 | `<test name>` |

## Risks and rollback
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| … | … | … | … |

- **Rollback:** …
