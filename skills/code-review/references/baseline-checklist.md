# Baseline review checklist

Fallback when no project skill or instruction covers a topic. Report only real, actionable problems.

## Correctness
- Logic matches the brief and the plan; acceptance criteria hold, including negative and edge cases.
- Boundary values: empty, null, zero, one, maximum; off-by-one; integer and float precision; rounding.
- Error paths: errors are handled or propagated deliberately, never swallowed; resources are released on failure.
- Concurrency: shared state, race conditions, ordering assumptions, re-entrancy.
- Time: time zones, clocks, durations, date arithmetic.

## Security
- Untrusted input validated at the boundary; no injection (SQL, shell, path, template, deserialization).
- Authorization checked on the server side for each resource; no secret or personal data in code, logs or errors.
- New dependencies: necessary, maintained, pinned.

## Performance
- No accidental quadratic loop, N+1 query, unbounded load in memory, or blocking call on a hot path.
- Timeouts on remote calls.

## Maintainability
- Follows the existing patterns and naming of the codebase; no dead code, duplicated logic or speculative abstraction.
- Public behavior changes are documented where the project documents them.

## Architecture docs
- New or changed integrations, flows, security rules, data stores and component boundaries are reflected in the architecture docs, with sources and Mermaid diagrams that match the code.
- New architecture decisions are recorded as ADRs; existing ADRs are respected or explicitly superseded.

## Tests
- Tests prove the behavior (they would fail without the change), are deterministic, and cover the acceptance criteria.
- Bug fixes include a regression test.

## UI (UI lots only)
- The project's components and tokens are reused; no new UI dependency without a reason in the plan.
- WCAG 2.1 AA: accessible names and labels, keyboard operation and visible focus, contrast, target sizes, no information by colour only.
- Every state of the plan's UX intent exists: loading, empty, error with recovery, success, disabled.
- Responsive on the project's breakpoints; user-facing strings go through the translation mechanism.
- The lot report gives visual evidence, or says why there is none.

## .NET performance (.NET projects only)
Rules and sources: `dotnet-performance` skill. Severity: the plan's for a `PERF-n`; otherwise the defaults below.
- **major:** tracking queries in read paths, N+1 queries, loading entities where a projection suffices, sync over async (`.Result`, `.Wait()`), `HttpClient` created per call, unbounded result sets.
- **major:** misuse of `ValueTask` (awaited twice, `.Result` before completion), `stackalloc` without a size guard or inside a loop, `ArrayPool` buffers not returned or read beyond the requested length, spans kept across `await`.
- **minor:** avoidable allocations on a hot path (boxing, closures, LINQ in tight loops), CA18xx warnings left, missing source-generated logging or JSON where the project uses them.
- A Tier B technique without a `PERF-n` or a measurement is a **minor** finding (unneeded complexity).

## Compatibility and operations
- Backward compatibility of APIs, files, schemas and configuration; migrations are safe.
- Logs and metrics are meaningful and free of sensitive data.
