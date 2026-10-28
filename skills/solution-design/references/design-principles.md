# Design principles and patterns

Use this checklist when no project architecture skill covers the topic. Prefer the patterns the codebase already uses.

## Principles
- **Cohesion and coupling:** each module has one reason to change; dependencies point from volatile code to stable code (business rules do not import frameworks, UI or infrastructure).
- **Explicit boundaries:** validate and translate data at the edges (API, files, database, external services); keep the core free of transport details.
- **Simple data flow:** prefer pure functions and immutable data for business rules; isolate side effects.
- **Error handling strategy:** decide where errors are detected, translated and reported; never swallow exceptions silently; fail fast on invalid input.
- **Configuration:** no hard-coded environment values or secrets; defaults are safe.
- **Naming:** domain vocabulary from the glossary; one concept, one name.
- **Backward compatibility:** public APIs, file formats, database schemas and events change through additive, versioned or migrated steps.

## Patterns: use when, avoid when
| Pattern | Use when | Avoid when |
|---|---|---|
| Strategy / polymorphism | Several interchangeable behaviors selected at runtime | Only one behavior exists today (YAGNI) |
| Adapter / anti-corruption layer | Integrating an external API or legacy model you do not control | The external model already matches the domain |
| Repository / gateway | Isolating persistence or remote access to test business rules | A thin script or a single query |
| Factory | Construction is complex or depends on configuration | A constructor call is enough |
| Decorator / middleware | Cross-cutting concerns (logging, retries, caching, auth) | The concern applies to a single call site |
| Observer / domain events | Decoupling side effects from the main flow | Ordering or transactional consistency is required |
| Result / error values | Expected failures are part of the business flow | Truly exceptional situations |

## Smells to flag in the options table
- A new layer that only forwards calls.
- Generic frameworks built for one use case.
- Shared mutable state across modules or threads.
- Duplicate sources of truth for the same data.
