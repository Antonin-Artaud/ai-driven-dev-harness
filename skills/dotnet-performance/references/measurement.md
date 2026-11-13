# Measurement

| Tier | Rule | When not, pitfalls | Version | Source |
|---|---|---|---|---|
| A | Profile the hot code paths before optimizing them. | — | not stated | https://learn.microsoft.com/en-us/aspnet/core/fundamentals/best-practices |
| B | Evidence for a Tier B change: BenchmarkDotNet with `[MemoryDiagnoser]`, before and after, reporting Mean, Allocated and Gen 0/1/2 per 1000 operations. | Not enabled by default; benchmarks that keep memory alive can run out of memory (use `IterationSetup`/`IterationCleanup`, `OperationsPerInvoke`). | not stated | https://benchmarkdotnet.org/articles/configs/diagnosers.html |
| B | First-level diagnosis with `dotnet-counters` (GC heap size, allocation rate, thread pool, exceptions); deeper with `dotnet-trace` or PerfView. | Counters readable from .NET 5 apps. | .NET 5 | https://learn.microsoft.com/en-us/dotnet/core/diagnostics/dotnet-counters |
| B | Allocation budgets in `PERF-n` requirements (bytes allocated per operation, queries per request), checked by a benchmark or a test. | Without a target or a measured problem, keep to Tier A. | — | https://learn.microsoft.com/en-us/aspnet/core/fundamentals/best-practices |
