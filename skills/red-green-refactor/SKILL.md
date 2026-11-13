---
name: red-green-refactor
description: 'Test-driven development discipline of the ai-delivery-workflow, for the builder and the implementer: red (write one failing test and watch it fail for the right reason), green (the minimal code that makes it pass), refactor (clean up with the suite green), one behavior at a time, with the red and green evidence reported per lot. Use only within this delivery workflow, when implementing or briefing a lot or a fix lot, or checking that a lot report proves the test came first.'
user-invocable: false
---

# Red-green-refactor

Tests drive the code: no production code is written without a failing test that asks for it. Project testing skills and instructions win over this skill (skill precedence of the `delivery-workflow` skill); this skill sets the discipline, the project sets the frameworks, levels and naming.

## The cycle

Take the next behavior from the lot (an acceptance criterion, a task, a finding to fix) and repeat until the lot is done:

1. **Red.** Write one test for one behavior, named after that behavior. Run it and watch it fail.
   - It must fail **for the right reason**: an assertion on the expected behavior, not a syntax error, a missing import or a broken fixture. A compilation error is acceptable only when the missing symbol is exactly what the test asks for.
   - A test that passes on first run proves nothing: either the behavior already exists (say so and move on) or the test is wrong (fix the test).
2. **Green.** Write the simplest production code that makes this test pass. Hard-coded values and obvious duplication are allowed at this step; the next tests force the generalization. Run the whole relevant suite: everything is green.
3. **Refactor.** With the suite green, remove duplication, clarify names and structure, in the production code and in the tests. No new behavior here. Run the suite after each step; if it turns red, undo the last step rather than debug forward.

Keep the steps small: when a test needs a lot of code to pass, write a smaller test first. Order the tests from the simplest case to the general one, then edge and error cases.

## Rules

- **Bug fixes start red:** reproduce the bug with a test that fails on the current code, then fix it. The same applies to review findings and PR comments that report wrong behavior.
- **Never weaken a test to get green:** do not delete, skip, comment out or loosen an assertion to make a test pass. If the test was wrong, say why in the lot report.
- **Behavior, not implementation:** test through the public interface of the unit; mock only the boundaries (network, clock, file system, external services), following the [pitfalls reference](./references/pitfalls.md).
- **Deterministic and fast:** no real time, randomness, network or test order dependency without control.
- **One lot, one commit** (see the `plan-execution` skill): the red, green and refactor steps happen in the working tree; the commit holds the tests and the code together. Do not commit a red suite.
- **When test-first is not feasible** (pure configuration, generated code, documentation, a spike agreed in the plan, code without any test harness), say so in the lot report with the reason and the alternative check you ran. Missing test infrastructure the lot needs is a `PLAN DEVIATION`, not a reason to skip tests silently.
- **Only the user waives the tests.** In the `build` and `feedback` phases, the `PreToolUse` hook asks the user to confirm any commit that changes code without a test file (gates reference of the `delivery-workflow` skill). Never rename files or split a commit to get around it. If the user denies the commit, write the failing test first; if the project has no test harness at all (a legacy project without unit or end-to-end tests), report a `PLAN DEVIATION` so that the user decides, once, between adding a harness and accepting lots without tests.

## Evidence in the lot report

The implementer adds a `TDD cycle` entry to the lot report of the `plan-execution` skill, one line per behavior:

```
TDD cycle:
- <behavior / acceptance criterion> — red: <test name> failed with <assertion message> — green: <command> → <n passed> — refactor: <what changed | none>
- Not test-first: <item> — <reason> — checked by <alternative>
```

## Builder role

The builder does not code, so it applies this skill through the implementer:

1. **Brief.** In every implementer prompt (lots and fix lots), require the red-green-refactor cycle of this skill and the `TDD cycle` entry, and list the acceptance criteria or findings each test must cover. When the user has accepted lots without tests (legacy project without a test harness), say so in the prompt: the commit hook still asks the user for each such commit.
2. **Check the report.** For each lot, every behavior has a red step that failed for the right reason, then a green run of the suite; every "not test-first" item has a credible reason. A missing or implausible red step (the test was written after the code, or failed only on an import error) sends the lot back to the implementer once with the gap named; if it recurs, record it as a deviation in the progress report.
3. **Review.** Tell the reviewer that the lots followed this skill, so that missing tests for an acceptance criterion or a bug fix without a regression test are reported.
