# Page guide

What each page of the architecture map must contain, and where to look in the code. Keep each page under about 150 lines; split by area when it grows.

## context.md
- The system in one sentence, its users and actors, the external systems it depends on or serves.
- One Mermaid `flowchart` (C4 level 1). Look at: README, authentication setup, HTTP clients, message brokers, configuration keys naming other systems.

## containers.md
- Each deployable or running unit (web app, API, worker, database, cache, queue, storage) with its technology and responsibility.
- How they communicate (protocol, sync or async). Look at: solution and project files, Dockerfiles, compose files, infrastructure as code, pipeline definitions.

## components.md
- Modules and layers of each container, their responsibility, and the allowed dependency directions (for example: domain depends on nothing).
- Where to put new code of each kind. Look at: folder structure, project references, dependency injection setup, architecture tests.

## integrations.md
- Table: system, purpose, protocol, authentication, owner or contact, timeout and retry policy, source file.
- One Mermaid `sequenceDiagram` per critical flow (payment, sign-in, synchronization...), including error and retry paths when the code handles them.
- Look at: HTTP and SDK clients, generated clients, webhooks and callbacks, message producers and consumers, configuration.

## data.md
- Stores and what each owns, main entities and relations (Mermaid `erDiagram` when useful), migrations location.
- Sensitive and personal data: where it is stored, encrypted, logged or exported; retention when known.

## security.md
- Authentication (identity provider, flows, tokens), authorization model (roles, policies, where checks happen), secrets management, trust boundaries, input validation strategy, security headers and CORS.
- Known threats or gaps as **To confirm** items. Never secrets, keys, internal URLs or personal data.

## quality.md
- Only measured or stated targets: latency, throughput, availability, limits. Logging, metrics, tracing and alerting setup; health checks; resilience patterns in place.

## glossary.md
- Domain terms used in the code and the business, one line each, with the code name when it differs.

## decisions/
- One ADR per significant decision, from the [ADR template](../assets/adr-template.md), numbered `0001`, `0002`... A new ADR that reverses an old one sets `supersedes`, and the old one gets `status: superseded`.
