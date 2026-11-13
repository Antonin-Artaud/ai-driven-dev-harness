# Performance checklist

Use when no project performance skill covers the topic. Performance work needs a target (from the brief) or a measured problem.

## Algorithms and data access
- Complexity of the hot paths with realistic volumes (from the brief); avoid accidental quadratic loops.
- N+1 queries or remote calls inside loops: batch, join or prefetch.
- Pagination or streaming for unbounded result sets; no full table or file loads in memory.
- Indexes for new query patterns; check the query plan when the data volume matters.

## I/O and concurrency
- Timeouts on every remote call; no blocking I/O on request threads or UI threads.
- Bounded concurrency (pools, queues) and back-pressure for bulk work.
- Avoid chatty protocols: fewer, larger calls.

## Caching
- Cache only with a clear invalidation rule and an acceptable staleness; measure the hit rate.
- Never cache per-user or sensitive data in a shared cache without proper keys.

## Memory and resources
- Release resources deterministically (files, connections, handles).
- Avoid unbounded collections, logs or queues.

## Measurement
- Define the metric (p95 latency, throughput, memory) and how to measure it: benchmark, profiler or production telemetry.
- Add a regression guard when the change targets performance (benchmark threshold or test on volume).
