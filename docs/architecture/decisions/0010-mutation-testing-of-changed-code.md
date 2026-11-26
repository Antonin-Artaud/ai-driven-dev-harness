---
title: 0010 — Mutation testing of the changed code, checked by the reviewer
status: accepted
date: 2026-11-26
supersedes: none
---
# 0010 — Mutation testing of the changed code, checked by the reviewer

## Context
The owner asked for mutation testing in the testing stage. Since 0.5.0 the `red-green-refactor` skill proves that each test failed once before the code, and the test-first gate (`PreToolUse`) proves that a code commit contains a test file. Neither proves that the tests pin the behavior: the hard-coded values of a green step, a branch added while refactoring or an assertion on a mock pass both checks. Line coverage has the same blind spot. Mutation tools are stack-specific (Stryker.NET, StrykerJS, PIT, mutmut, Infection, cargo-mutants...), a run takes minutes rather than seconds, and legacy code around a change usually has many surviving mutants the lot did not create.

## Decision
- The method lives in a `mutation-testing` skill ([ADR 0001](./0001-method-in-skills.md)), loaded by the builder, the implementer, the ui-ux-designer and the reviewer. Its tools reference gives, per tool, the run on changed files, the report, the in-code disable syntax and the folders to keep out of git, each with its sources.
- **Opt-in per project:** a Mutation testing part of the project contract (`AGENTS.md`) gives the mode (`gate`, `report` or `off`), the tool, the command, the report and the threshold (80% by default, the "high" threshold Stryker uses by default). Without it, mutation testing is off. Only the user changes the mode or lowers the threshold.
- **Changed code only:** the implementer mutates the files of its lot once the lot is green, before the commit; the reviewer mutates the files of the branch once per review iteration. The gate is the **mutation score of the changed lines**: detected (killed + timeout) / valid (detected + survived + no coverage), with the mutation-testing-elements definitions. Mutants on lines nobody changed are reported apart and never block.
- **Surviving mutants** are killed with behavior tests (the mutant is the red step of the `red-green-refactor` cycle), or disabled in the code with the tool's comment and a reason when they are equivalent; the reviewer reads every disable comment.
- **A deterministic gate script**, `skills/mutation-testing/scripts/mutation_gate.py` (standard library, [ADR 0003](./0003-standard-library-python-hooks.md)), reads the two widespread report formats (mutation-testing-elements JSON, PIT `mutations.xml`), keeps the mutants of the lines changed since the merge base (plus untracked files), computes the score, lists survivors and disabled mutants, flags changed code files absent from the report, and refuses a mutation-testing-elements report whose source differs from the working tree. Tools with another report use their own changed-code mode.
- **Enforced by the reviewer's verdict, not by a hook:** in `gate` mode a score below the threshold, an unjustified disable comment or a changed file left out of the run is a major finding, so the existing review gate (`APPROVED` for HEAD) carries it. A surviving mutant in code that enforces a `SEC-n` requirement takes that requirement's severity.
- **Onboarding** detects the stacks from their marker files, proposes the tool and adds its output folders to `.git/info/exclude`, so that a run does not trip the review gate's clean tree check.

## Consequences
- The suite of every lot is checked against its own code, and the review findings name the missing assertions (file, line, mutator).
- Builds get slower: one scoped run per lot and one per review iteration. Small lots and scoped runs keep it to minutes; the reviewer's run is the price of not trusting the lot reports.
- The mutation tool is a new development dependency of the target project, installed only with the user's agreement.
- The threshold is only as honest as the disable comments: the reviewer checks them, and the gate script lists them.
- Equivalent mutants and unreachable code can still make the threshold out of reach; the implementer reports a `PLAN DEVIATION` instead of forcing the gate.

## Alternatives considered
- **A hook that checks the score:** a mutation run does not fit the 15 s hook timeout, and a hook could only read a report the agent produced; the reviewer reruns the tool instead, as it already reruns the tests.
- **Whole-project score:** slow on every lot and dominated by legacy code the lot did not touch.
- **A coverage threshold:** coverage does not check assertions.
- **A dedicated mutation agent:** agents stay thin; the implementer must kill the survivors in its own lot, and the reviewer already gives the independent check.
- **Reviewer only:** survivors would be found after the lots are committed, spending one of the two review iterations on them.
- **The tools' own thresholds (`break`, `mutationThreshold`):** they apply to the whole run, including unchanged code; they stay available to the team's CI.
