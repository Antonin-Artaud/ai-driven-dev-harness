# Architecture decisions

One record per significant decision, numbered `0001`, `0002`..., written from the ADR template of the `architecture-mapping` skill. Records 0001 to 0005 were backfilled on 2026-11-13 from the design of 0.1.0.

| ADR | Decision |
|---|---|
| [0001](./0001-method-in-skills.md) | The method lives in skills, agents stay thin |
| [0002](./0002-azure-devops-through-mcp-only.md) | Azure DevOps through the MCP servers only |
| [0003](./0003-standard-library-python-hooks.md) | Hooks in Python, standard library only |
| [0004](./0004-cross-family-reviewer.md) | A reviewer from another model family |
| [0005](./0005-ai-folder-not-committed.md) | The `.ai/` working folder is never committed |
| [0006](./0006-validated-state-transitions.md) | Validated `state.json` transitions and hook-owned state |
| [0007](./0007-specialist-agents.md) | Specialist agents: UI designer under the builder, security and performance under the architect |
| [0008](./0008-stack-specific-performance-skills.md) | Stack-specific performance skills in two tiers, grounded in a documentation MCP server |
| [0009](./0009-rename-ai-driven-dev-harness.md) | The plugin is renamed `ai-driven-dev-harness` |
