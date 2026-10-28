---
title: Architecture map
verified_on: <YYYY-MM-DD>
sources: []
---
# Architecture map

Short, sourced map of the application. Every statement cites the code it comes from; what the code does not prove is marked **To confirm**. The pages are kept up to date in the same pull request as the code they describe.

## Pages

| Page | Covers |
|---|---|
| [Context](./context.md) | Actors, the system, external systems |
| [Containers](./containers.md) | Applications, stores, queues, deployment units |
| [Components](./components.md) | Modules, layers, allowed dependencies |
| [Integrations](./integrations.md) | External APIs and sequence diagrams of critical flows |
| [Data](./data.md) | Data model, stores, sensitive data |
| [Security](./security.md) | Authentication, authorization, secrets, trust boundaries |
| [Quality](./quality.md) | Performance, reliability, observability |
| [Glossary](./glossary.md) | Domain terms |
| [Decisions](./decisions/) | Architecture decision records |

Remove the rows of the pages that do not exist yet.

## To confirm

- <open item, page>

## How to update

- In a delivery: the plan lists the pages to change under **Documentation impact**, and the same pull request updates them.
- Outside a delivery: run the `architecture-mapping` skill with `--refresh`.
