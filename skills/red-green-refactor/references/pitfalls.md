# Red-green-refactor pitfalls

Use when a cycle feels slow, a test is hard to write, or a lot report looks suspicious.

## Red step
- **Test after the fact:** the code exists before the test, the test passes on first run. Fix: revert or stash the code, watch the test fail, restore the code.
- **Wrong red:** the test fails on an import error, a typo or a broken fixture, not on the expected behavior. Fix: make the test compile and run, then check that the failure message names the missing behavior.
- **Too big a test:** one test covers several behaviors and needs a lot of code to pass. Fix: split it, start with the simplest case.
- **Unclear failure message:** the failure does not say what was expected. Fix: assert on values with a message, one behavior per test.

## Green step
- **Gold plating:** code for cases no test asks for yet. Fix: delete it or write the test that asks for it first.
- **Changing the test to pass:** loosening an assertion, adding a skip, catching the exception in the test. Fix: never; if the test is wrong, correct it and explain why.
- **Running only the new test:** a regression elsewhere goes unnoticed. Fix: run the relevant suite at every green step, and the full project test command before the commit.

## Refactor step
- **Skipping it:** duplication and hard-coded values from the green step stay in the commit. Fix: refactor once green, in the code and in the tests.
- **Refactoring while red:** behavior and structure change together and failures become hard to read. Fix: get back to green first.
- **Refactoring outside the lot:** a cleanup sweep in unrelated files. Fix: keep it to the code the lot touches (`plan-execution` skill).

## Test doubles
- Mock the boundaries (network, clock, file system, external services, message brokers), not the unit under test or its private collaborators.
- Prefer fakes and in-memory implementations over call-by-call mock expectations: they test behavior, not the call sequence.
- A test that only asserts that a mock was called restates the implementation; assert on the observable outcome instead.

## Legacy code without tests
- Before changing it, write a characterization test that pins the current behavior (it passes: this is the safety net, not the red step).
- Then apply the cycle to the change itself: a failing test for the new or fixed behavior first.
