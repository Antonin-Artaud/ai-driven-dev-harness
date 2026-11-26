# Testing strategy checklist

Use when no project testing skill covers the topic.

## Coverage of the brief
- Every acceptance criterion maps to at least one automated test, named after the behavior it checks.
- Bug fixes start with a test that fails before the fix and passes after it.
- Negative and edge cases from the brief have their own tests.

## Test levels
- **Unit:** business rules and pure logic, fast and deterministic; most tests live here.
- **Integration:** boundaries with the database, the file system, external APIs or messaging, using the project's test doubles or containers.
- **End-to-end:** only for critical user journeys; keep them few.
- **Contract:** when another team or service consumes or provides an API.

## Test quality
- Deterministic: no dependency on time, randomness, network or test order without control (fixed clock, seeds, fakes).
- Readable: arrange, act, assert; one behavior per test; meaningful failure messages.
- Test data: minimal, built in the test or through the project's builders or fixtures; no production data.
- Do not test implementation details that the plan may change; test behavior.

## Mutation testing
- When the project contract turns it on (`mutation-testing` skill), every lot that changes production code is mutated: keep the logic of each lot reachable by fast tests, so that its mutants can be killed within the lot.
- Name the code where a surviving mutant matters most: acceptance criteria, `SEC-n` checks, boundaries and error paths.
- The threshold and the mode come from the contract; only the user changes them. Excluding code from mutation (generated code, migrations) belongs in the tool configuration, with a reason, not in a lot.

## Verification commands
- Use the build, lint and test commands from the project contract; note the ones the implementer must run per lot.
