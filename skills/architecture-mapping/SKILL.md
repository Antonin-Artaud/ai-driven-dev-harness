---
name: architecture-mapping
description: 'Map a project''s application into committed architecture docs (docs/architecture/ by default): C4 context and containers, components, external integrations with Mermaid sequence diagrams, data, security, quality attributes, glossary and ADRs, each statement sourced from the code. Use for the initial mapping during project-onboarding, for an explicit --refresh of docs/architecture, or when an ai-delivery-workflow agent reads or updates docs/architecture during a delivery.'
argument-hint: 'Optional: --refresh, or the pages to (re)map'
---

# Architecture mapping

Goal: a short, sourced map of the application that the architect starts from and that every workflow PR keeps up to date. A wrong map is worse than no map: the agents would trust it.

## Location

The pages live in the folder named by the `Architecture docs` line of the project contract (`AGENTS.md`), `docs/architecture/` by default. When the project already documents its architecture elsewhere, point the contract to that folder or link the existing pages instead of duplicating them.

## Pages

| Page | Content |
|---|---|
| `README.md` | Index: pages, what each covers, open "To confirm" items, how to update |
| `context.md` | C4 level 1: actors, the system, external systems (Mermaid `flowchart`) |
| `containers.md` | C4 level 2: applications, databases, queues, deployment units and how they talk |
| `components.md` | Modules and layers, allowed dependencies, where each responsibility lives |
| `integrations.md` | Table of external APIs and services, then one Mermaid `sequenceDiagram` per critical flow |
| `data.md` | Data model, stores, ownership, sensitive data and retention |
| `security.md` | Authentication, authorization, secrets handling, trust boundaries, known threats |
| `quality.md` | Performance, reliability and observability: known targets, measures and limits |
| `glossary.md` | Domain terms, one line each |
| `decisions/NNNN-<title>.md` | Architecture decision records, numbered in order |

Create a page only when the project has something to say about it. What each page must contain: [page guide](./references/page-guide.md).

## Rules for every page

1. **Source every statement.** Each component, arrow, integration and rule names the file or folder it comes from (`src/payments/client.ts`). List the folders the page describes in its front matter `sources`.
2. **Never guess.** What the code does not prove is marked `**To confirm:**` and listed in `README.md`. Never invent an API call, a flow or a target.
3. **Front matter.** Start each page from the [page template](./assets/page-template.md): `title`, `verified_on` (date of the last check against the code) and `sources`. The last commit touching a page is its verification point: `git log -1 --format=%H -- <page>`.
4. **Mermaid only** for diagrams, kept small (about 15 nodes at most; split otherwise). Azure Repos and GitHub render it, and it diffs as text.
5. **Short and factual.** Describe what exists, not what should exist; decisions and their reasons go to ADRs.
6. **No secrets or internal endpoints:** describe mechanisms, never credentials, keys, internal URLs or personal data.
7. Write the pages in the language of the project documentation (default: English).

## Initial mapping (onboarding)

1. Run the `project-onboarding` script with `--docs` (and `--docs-path` when the contract names another folder): it creates the folder, `README.md` and `decisions/` without overwriting anything.
2. Read the existing documentation first (README, `docs/`, wiki, ADRs), then the code: entry points, configuration, dependency manifests, infrastructure files, HTTP clients, message consumers, database access, authentication middleware.
3. Map in this order, and stop after the pages that matter for the project: `context`, `integrations`, `security`, `containers`, `components`, `data`, `quality`, `glossary`.
4. Show the user the pages and the "To confirm" list before writing. Iterate until they validate.
5. Commit on a dedicated branch (`docs/architecture-map`) and let the user open the PR through the team's usual process. Never commit the map directly on the base branch.

## Refresh (`--refresh`)

For drift that happened outside the workflow:

1. For each page, take its verification point (`git log -1 --format=%H -- <page>`) and list the changes since: `git diff --stat <sha>..HEAD -- <sources>`.
2. Re-check only the pages whose sources changed, plus their "To confirm" items.
3. Update the pages and `verified_on`, show the diff to the user, and commit on a dedicated branch as above.

## Reading the map (architect, reviewer)

1. Read `README.md`, then the pages the brief touches.
2. Compute the drift of each page used (refresh step 1). When its sources changed, check the code before relying on the page, and report any contradiction as a risk.
3. Treat existing ADRs as constraints: contradicting one requires saying so explicitly and recording a new ADR that supersedes it.

## Updating the map in a delivery

The workflow keeps the map current in the same PR as the code:

- The architect adds a **Documentation impact** section to `plan.md`: the pages and diagrams to change, the ADR to add, or `none` with the reason.
- `none` is right for changes without architectural effect: wording, labels, styles, translations, tests only, internal refactoring that keeps the same components, flows and rules.
- The implementer applies the impact in the lot it belongs to (or in a final documentation lot) and updates `verified_on` on the pages it checked.
- The reviewer checks that the pages match the diff (`code-review` skill).
