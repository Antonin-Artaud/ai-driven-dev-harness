---
name: mutation-testing
description: 'Mutation testing step of the ai-driven-dev-harness, for the builder, the implementer, the ui-ux-designer and the reviewer: once a lot is green, run the project''s mutation testing tool on the changed code, kill the surviving mutants with tests or disable the equivalent ones in the code with a reason, and check the mutation score of the changed lines against the threshold of the project contract with the mutation_gate.py script. Use only within this delivery workflow, when implementing, briefing or reviewing a lot.'
user-invocable: false
---

# Mutation testing

Red-green-refactor proves that each test failed once. Mutation testing proves that the suite pins the code: the tool makes small changes to the production code (**mutants**: `>=` into `>`, `&&` into `||`, a removed call, a constant return value) and runs the tests against each one. A mutant that makes a test fail is **killed**; a mutant no test notices **survives**, and points to a behavior no assertion checks. Line coverage cannot tell the difference: a line run by a test that asserts nothing is covered, and its mutants survive.

Project testing skills and instructions win over this skill (skill precedence of the `delivery-workflow` skill): the project contract sets the tool, the command and the threshold; this skill sets the procedure.

## Settings (project contract)

The **Mutation testing** part of the "AI delivery workflow" section of `AGENTS.md` (template of the `project-onboarding` skill):

| Setting | Meaning | Default |
|---|---|---|
| Mode | `gate`: the threshold is enforced (the reviewer requests changes below it); `report`: run and report, never blocking; `off`: not run, with the reason | `off` when the part is missing |
| Tool | The mutation testing tool of the stack ([tools reference](./references/tools.md)) | — |
| Command | How to run it on a list of files, and from which folder | — |
| Report | Path of the report and its format: `mutation-testing-elements` JSON or `pitest-xml` (read by the gate script), otherwise `tool` | — |
| Threshold | Minimum mutation score of the changed lines, in percent | 80 (the "high" threshold Stryker uses by default) |
| Not mutated | Code excluded in the tool configuration (generated code, migrations...) | none |

Only the user changes the mode or lowers the threshold, as only the user waives tests (`red-green-refactor` skill). When the part is missing, mutation testing is off: say so in the lot report.

**Mutation score of the changed lines** = detected / valid, over the mutants located on lines the lot or the branch added or changed. Detected = killed + timeout; valid = detected + survived + no coverage. Mutants disabled in the code (ignored), compile errors and runtime errors stay out of the score; mutants not run (pending) fail the gate. Mutants on lines nobody changed are reported apart and never block: the lot is not asked to fix old code.

## When

- **Implementer and ui-ux-designer:** once per lot and fix lot, after the last refactor step with the suite green, before the commit. Not at every red-green step: a mutation run is much slower than the tests.
- **Reviewer:** once per review iteration, on the whole branch.
- Always scoped to the changed files, never the whole project.

## Procedure (implementer and ui-ux-designer)

1. **Scope.** The production code files the lot changed: `git diff --name-only HEAD` plus `git ls-files --others --exclude-standard`, minus the test files. When the lot changes no production code (tests, documentation, configuration only), write `Mutation testing: not applicable — <reason>` and stop.
2. **Run the tool** with the contract's command on these files, whole files: the gate script keeps the changed lines, while a line range would miss the mutants of the other hunks. The [tools reference](./references/tools.md) gives each tool's file filter. The tool first runs the suite without mutants: if it fails there, fix the suite (or report it), it is not a mutation result.
3. **Evaluate the changed lines** with [mutation_gate.py](./scripts/mutation_gate.py), called with its absolute path (resolve it from this file's folder):
   ```
   python <path>/mutation_gate.py --repo . --report <report from the contract> --base HEAD --threshold <threshold>
   ```
   (`python3` on Linux and macOS). It prints a JSON summary: `score`, `counts`, `survivors` (file, line, mutator, replacement), `ignored` (with their reasons), `not_in_report` (changed code files the run did not mutate) and a one-line `summary`. Exit code 0: passed; 2: below the threshold, or mutants not run; 1: the report cannot be used (unreadable, unknown format, or older than the code: rerun the tool). With a `tool` report format, use the tool's own changed-code mode and threshold (tools reference) and compute the same score from its output.
4. **Handle each surviving or uncovered mutant on a changed line**, the riskiest first (acceptance criteria, `SEC-n` checks, boundaries, error paths):
   - **Kill it** with a test of the behavior the mutant breaks: a boundary value, the other branch, an assertion on the returned value or on the observable side effect, through the public interface of the unit (`red-green-refactor` skill). Here the mutant is the red step: the new test passes on the real code, and the rerun shows the mutant killed.
   - **Disable it in the code** only when it is equivalent (no test can tell it from the real code: same observable behavior) or unobservable by design (the text of a log message, a defensive branch the plan keeps), with the tool's disable comment (an exclusion in the tool configuration for PIT) and **the reason written next to it** (tools reference). The reviewer reads every one of them.
   - **Never** weaken the code or a test to escape a mutant, disable a mutant to pass the gate, exclude a changed file from the run, or change the threshold. A mutant that reveals dead or unreachable code: remove that code (within the lot) instead of testing it.
5. **Rerun and evaluate again** until the gate passes (`gate`) or every survivor is killed or explained (`report`). If the threshold stays out of reach (for example code that only a slow end-to-end test exercises), stop and report a `PLAN DEVIATION` with the survivors, the options and their cost; never commit a lot below the threshold without saying so.
6. **Leave the tree clean.** `git status --porcelain` shows only the lot's own changes. The tool's output goes to folders git ignores (onboarding adds them to `.git/info/exclude`); delete anything it left elsewhere and never commit it. After a tool that mutates files in place, check `git diff` for a leftover mutant before committing.

### Lot report entry

The implementer adds a `Mutation testing` entry to the lot report of the `plan-execution` skill, and one TDD cycle line per mutant killed:

```
Mutation testing: <mode> — <tool> on <files> — <summary of the gate script> — killed by new tests: <n> — disabled in the code: <file:line mutator — reason | none>
                  | not applicable: <reason> | off: <reason from the contract | not configured>
TDD cycle:
- <behavior the mutant breaks> — red: mutant <file:line mutator> survived — green: killed by <test name>
```

## Builder role

The builder does not code, so it applies this skill through the implementer and the reviewer:

1. **Brief.** In every implementer and ui-ux-designer prompt (lots and fix lots), give the settings of the contract (mode, tool, command, report, threshold) and require the procedure above and the `Mutation testing` entry. When the contract has no Mutation testing part, tell the user once that mutation testing is off and that the `project-onboarding` skill can set it up.
2. **Check the report.** In `gate` mode, a lot whose entry is missing, whose summary is below the threshold without a `PLAN DEVIATION`, or that disables a mutant without a reason goes back to the implementer once, with the gap named; if it recurs, record it as a deviation in the progress report.
3. **Review.** Tell the reviewer the mode and the threshold.
4. **PR.** Report the reviewer's mutation summary in the PR description (`azure-devops` skill template, "How it was verified").

## Reviewer role

1. **Verify, do not trust the lot reports.** Run the tool on the production files of `git diff --name-only <base_sha>..HEAD`, then the gate script with `--base <base_sha>`. Leave the tree as you found it: the tool's output stays in git-ignored folders.
2. **Findings:**

   | Situation | `gate` | `report` |
   |---|---|---|
   | Score of the changed lines below the threshold, or mutants not run | major | minor |
   | Surviving mutant in code that enforces a `SEC-n` requirement | severity of the requirement in the plan | same |
   | Mutant disabled in the code without a credible reason (it is not equivalent) | major | minor |
   | Changed code file missing from the report (`not_in_report`) without a reason in the lot report | major | minor |
   | The tool cannot run, unless it also fails on the base branch | major | minor |
   | Other surviving mutants on changed lines | minor | minor |

   Each finding gives `file:line`, the mutator and its replacement, and the test that would kill it.
3. **Write** the summary of the gate script in the `Verification` section of `review.md`, with the command you ran.

## Pitfalls

- **Slow runs:** keep the scope to the changed files, use the tool's incremental mode when it has one, and keep lots small (`solution-design` skill). A lot that takes more than about 15 minutes to mutate reaches slow tests or is too big: say so in the lot report.
- **Flaky tests** make mutants look killed: fix the flakiness first (deterministic tests, `red-green-refactor` skill).
- **Timeouts** count as detected (an infinite loop is a detection). Many timeouts mean the tool's timeout is too short for the suite.
- **Equivalent mutants** are rare in code written test-first; many "equivalent" claims usually hide a missing assertion.
- **Assertions on mocks:** a test that only checks that a mock was called lets most mutants of the result survive; assert on the observable outcome.
- **Reports in the working tree:** an output folder git does not ignore trips the review gate of the hooks (uncommitted changes); rerun onboarding or add the folder to `.gitignore` through the team's usual PR.
