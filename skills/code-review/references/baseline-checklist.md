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

## Tests
- Tests prove the behavior (they would fail without the change), are deterministic, and cover the acceptance criteria.
- Bug fixes include a regression test.

## Compatibility and operations
- Backward compatibility of APIs, files, schemas and configuration; migrations are safe.
- Logs and metrics are meaningful and free of sensitive data.
