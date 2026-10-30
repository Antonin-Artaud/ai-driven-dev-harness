---
name: plan-execution
description: 'Execute a validated plan.md. Builder: orchestrate implementer and reviewer subagents lot by lot (adaptive: one subagent for a single lot, one per lot otherwise), run the bounded review loop, push and open the Azure Repos draft PR. Implementer: code one lot test-first, commit it and report deviations. Use when implementing a plan, delegating lots, fixing review findings or handling a plan deviation.'
---

# Plan execution

## Builder procedure

1. **Preconditions.** Read `.ai/current`, `state.json`, `brief.md`, `plan.md` and the project contract. The plan must be validated by the user. On the `fast` path without a plan, write a single-lot `plan.md` from the plan template of the `solution-design` skill, then proceed (the user chose the fast path on a validated brief).
2. **Branch.** The working tree must be clean (`git status --porcelain` empty; `.ai/` is excluded from git): otherwise stop and ask the user to commit or stash the unrelated changes. Then `git fetch origin` and `git switch -c ai/<slug> origin/<base_branch>` (or `git switch ai/<slug>` when it exists). Never work on the base branch. Record `branch`, set `phase: build` and `review_iterations: 0`.
3. **Delegate the lots** to the `implementer` subagent:
   - one lot in the plan: a single implementer run;
   - several lots: one implementer run per lot, sequentially, in plan order.
   The subagent does not see this conversation. Give it the slug, the lot number, the paths of `brief.md` and `plan.md`, the build and test commands, the architecture docs folder, every decision taken since the plan was written, and the requirement to follow the `red-green-refactor` skill. After each lot, check the report: tests green, a red step before the code for each behavior (`TDD cycle`), exactly one new commit, the documentation impact of the lot applied, deviations. Stop and escalate on any `PLAN DEVIATION` that changes the scope, the design or the acceptance criteria.
4. **Review loop.**
   - Once all lots are committed, run the `reviewer` subagent on `<merge-base>..HEAD` and increment `review_iterations`.
   - `APPROVED`: continue.
   - `CHANGES_REQUESTED`: send the blocker and major findings to an `implementer` run as a fix lot, then review again.
   - After 2 reviews still requesting changes, stop: set `phase: escalated`, then summarize the open findings and the options for the user.
5. **Prepare the PR description** in `pr-description.md` following the `azure-devops` skill (at most 4000 characters).
6. **Push:** `git push -u origin ai/<slug>`; the user confirms. Never force push.
7. **Open the draft PR** with `repo_pull_request_write` (`create`, `isDraft: true`, `workItems` when `state.work_item` is set) as described in the `azure-devops` skill. Record `pull_request` and set `phase: pr-open`.
8. **Post the minor findings** of `review.md` as PR comments starting with `🤖`, one thread per finding, anchored to the file and line when possible.
9. **Report:** PR link, lots and commits, tests, review verdict and iterations, deviations, and the next steps for the user: review the draft in Azure DevOps, comment there, use the **Address PR feedback** handoff, and publish the PR once satisfied.

## Implementer procedure

1. Read `brief.md`, `plan.md` (your lot, plus the context and decision sections), the project contract, and the instructions and skills that apply to the files you touch.
2. Implement the tasks of your lot test-first, following the `red-green-refactor` skill: for each behavior, a failing test, the minimal code to pass, then refactoring with the suite green (a failing test that reproduces the bug for a fix). Only the tasks of your lot: no unrelated refactoring, formatting sweep or dependency upgrade.
3. **Apply the documentation impact of your lot** (the `Documentation impact` section of `plan.md`), following the page rules of the `architecture-mapping` skill: sourced statements, Mermaid diagrams, `verified_on` set to today on each page you checked, new ADRs from its template. If the code you wrote changes an integration, a flow, a security rule, a data store or a component boundary that the plan did not list, update the page too and report it as a deviation.
4. Run the build, lint and test commands of the project contract. Fix the failures your change causes; report pre-existing failures without fixing them.
5. Commit once per lot, documentation included: stage the lot's files only and use the commit message of the plan (`<type>(<scope>): <summary>`). Do not mention work item IDs in commit messages and never use closing keywords.
6. Never push, never write under `.ai/`, never rewrite shared history (`--amend` only on your own lot commit, no `rebase -i`, no `reset --hard`).
7. **Plan deviation protocol:** if the plan is wrong, incomplete or impossible, stop and report `PLAN DEVIATION` with the evidence and the options. Small adjustments that change neither the scope, nor the design, nor the acceptance criteria (a helper name, an extra test) are allowed but must be listed.

### Lot report (returned to the builder)

```
Lot: <n> — <title>
Commit: <sha> <message>
Files changed: <list>
Tests added or updated: <list, mapped to acceptance criteria>
TDD cycle: <per behavior: red test and failure, green run, refactor | not test-first: reason and alternative check>
Documentation updated: <pages and ADRs | none (as planned)>
Commands run: <command> → <result>
Deviations: <none | list>
Notes for the reviewer: <risky spots, trade-offs>
```
