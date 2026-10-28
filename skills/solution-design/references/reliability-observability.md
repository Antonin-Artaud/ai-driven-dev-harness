# Reliability and observability checklist

Use when no project reliability or operations skill covers the topic.

## Failure modes
- List what happens when each dependency is slow, unavailable or returns invalid data.
- Timeouts everywhere; retries only for transient errors, with exponential backoff, jitter and a cap.
- Retried operations must be idempotent (idempotency keys, upserts, deduplication).
- Graceful degradation: a clear behavior when an optional dependency fails.
- Partial failures in batches: report per item, resume safely.

## Data changes
- Schema and data migrations are reversible or have a tested rollback; deploy them in backward-compatible steps (expand, migrate, contract).
- Long-running migrations are resumable and observable.

## Release safety
- Feature flag or configuration switch for risky behavior changes, with a default that keeps the current behavior.
- Rollback plan: what to revert, and in which order.

## Observability
- Structured logs at the right level, with correlation identifiers and without sensitive data.
- Metrics for the new behavior (rate, errors, duration) and, when relevant, an alert with a clear owner and action.
- Tracing across service boundaries when the project already uses it.
