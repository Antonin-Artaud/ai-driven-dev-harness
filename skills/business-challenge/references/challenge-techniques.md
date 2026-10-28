# Challenge techniques

Pick the techniques that fit the request. Each one lists the question to ask yourself and what to look for.

## Problem before solution
- Rewrite the request without any solution word (screen, button, table, endpoint, field).
- Ask: "What happens today, to whom, and what does it cost?" If nobody can describe the current pain, the need is not ready.

## 5 whys
- Ask "why" until you reach a business outcome (revenue, cost, risk, compliance, user satisfaction), usually 3 to 5 times.
- Stop when the answer stops changing the scope. Write the final "why" in the brief.

## Jobs-to-be-done
- Template: "When <situation>, I want to <motivation>, so that I can <outcome>."
- Use it to find the real user and to spot requests that serve a proxy (a manager, a report) rather than the user.

## Impact mapping
- Goal → actors → impacts (behavior changes) → deliverables.
- A deliverable that maps to no impact is a candidate for the out-of-scope list.

## Example mapping
- For each business rule, write concrete examples, including counter-examples, and note the open questions.
- Examples become the Given/When/Then acceptance criteria.

## Simpler alternatives and inversion
- Could we not build it: configuration, documentation, a process change, an existing feature?
- What is the smallest slice that delivers most of the value? Prefer vertical slices that can ship alone.
- Inversion: "How would we make this fail for sure?" then make sure the brief prevents it.

## Pre-mortem
- "Three months after release, this change is considered a failure. Why?" List the top 3 causes and turn each into a question, a criterion or a risk.

## Edge cases checklist
- Empty, null, zero, one, many, maximum sizes; duplicates; ordering.
- Permissions and roles; multi-tenant or multi-user conflicts; concurrent updates.
- Dates, time zones, locales, encodings, rounding and currency.
- Partial failures, retries, idempotency, timeouts, offline or degraded dependencies.
- Migration of existing data and backward compatibility of APIs or files.

## Non-functional prompts
- Performance: expected volume, latency, frequency, growth.
- Security and privacy: sensitive data, personal data, authentication, authorization, audit.
- Compliance: regulatory or contractual constraints.
- Operability: monitoring, alerting, support, rollback.
- Accessibility and usability when there is a user interface.

## Measuring success
- Name the metric, its baseline and the target, or state that success is binary (the bug no longer occurs).
- If success cannot be observed, ask how the team will know the change worked.
