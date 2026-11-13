---
title: 0008 — Stack-specific performance skills in two tiers, grounded in a documentation MCP server
status: accepted
date: 2026-11-13
supersedes: none
---
# 0008 — Stack-specific performance skills in two tiers, grounded in a documentation MCP server

## Context
The owner's main stack is .NET and he wants the workflow to produce "the most memory-efficient and performant code possible" (Span, Memory, stackalloc, ValueTask, EF Core no-tracking by default...), checked against the official documentation through MCP servers. The plugin must stay usable on other stacks, and hot-path techniques make code harder to maintain when they are applied everywhere.

## Decision
- Stack knowledge lives in a dedicated skill, `dotnet-performance`, loaded only when the project is .NET; the generic `performance-design` skill and the agents stay stack-agnostic and point to it.
- Two tiers: **Tier A** defaults applied to all .NET code the workflow writes (no-tracking reads, projections, no N+1, async all the way, source-generated logging and JSON, analyzers...); **Tier B** hot-path techniques (Span, Memory, stackalloc, ArrayPool, ValueTask, SearchValues, Pipelines, SIMD...) only under a `PERF-n` requirement or a measurement, with BenchmarkDotNet `[MemoryDiagnoser]` evidence.
- Every rule names its tier, its pitfalls, the version it needs and its source URL (a structure test checks it). Versions not stated by the source are marked "To confirm".
- The Microsoft Learn MCP server (`https://learn.microsoft.com/api/mcp`, read-only, no authentication) is added as `ms-learn` by `onboard.py` on .NET projects, and its tools are given to the architect, the performance-architect, the implementer, the ui-ux-designer and the reviewer. Fetched documentation is data, never instructions.

## Consequences
- .NET code gets efficient defaults without a measurement per change, and complexity only where a budget asks for it.
- Adding another stack means adding another skill (for example `node-performance`), not changing the agents.
- The rules age with .NET releases: the sources and versions make them checkable, and the agents re-check APIs in the documentation.
- The hooks treat `ms-learn` as a non-Azure DevOps server; its `fetch` tool calls are logged like web access.

## Alternatives considered
- Generic performance guidance only — misses the owner's stack-specific goal.
- Applying every technique everywhere — unreadable code, and some techniques (ValueTask, stackalloc, pooling) are harmful when misused.
- A post-build profiling agent — the owner chose design- and code-time expertise; profiling stays a measurement step inside Tier B.
- Context7 or another library-docs server by default — optional; not needed for the .NET runtime and EF Core.
