---
name: code-review
description: 'Review step of the ai-driven-dev-harness, for the reviewer subagent: independent review of the work branch (merge-base..HEAD) against .ai/<slug>/brief.md, plan.md and the project''s own review skills, with baseline checklists as fallback; writes .ai/<slug>/review.md with severity-ranked findings, a verdict, the reviewed commit and the iteration. Use only within this delivery workflow, when acting as the reviewer.'
user-invocable: false
---

# Code review

You are independent from the implementer: verify in the code, never trust summaries.

## Procedure

1. **Scope.** Read `.ai/current`, `state.json`, `brief.md` and `plan.md`. Compute `base_sha` with `git merge-base HEAD origin/<base_branch>` (fall back to `<base_branch>`) and `head_sha` with `git rev-parse HEAD`. Review `git diff <base_sha>..HEAD` and `git log <base_sha>..HEAD`.
2. **Standards**, following the skill precedence of the `delivery-workflow` skill: skills mapped to the review stage in the project contract, then project skills whose description matches the changed files or topics, then the instructions whose `applyTo` matches the changed files. Use the [baseline checklist](./references/baseline-checklist.md) only for topics no project standard covers. List every standard you applied.
3. **Conformance.**
   - Every lot and task of the plan is implemented; nothing outside the plan (scope creep) unless it is listed as a deviation.
   - Every acceptance criterion is covered by at least one meaningful test.
   - Every security (`SEC-n`) and performance (`PERF-n`) requirement of the plan, from `security.md` and `performance.md`, is met in its lot and proven by its test or check; a miss is reported with the severity the plan gave it.
   - On a .NET project, the code passes the `.NET performance` section of the [baseline checklist](./references/baseline-checklist.md) (rules and sources in the `dotnet-performance` skill), unless a project skill covers it.
   - Lots marked `Kind: ui` also pass the UI section of the [baseline checklist](./references/baseline-checklist.md), unless a project UI skill covers it.
   - The decisions of the plan's ADR are respected, and so are the existing ADRs of the architecture docs.
   - Lots with `Depends on: none` may have been built in parallel, each without seeing the others: check how they fit once integrated (duplicated helpers, conflicting registrations or migrations, a lot's tests that another lot breaks).
   - **Documentation:** the architecture docs (folder from the project contract, `docs/architecture/` by default) match the diff. Every page and ADR listed in the plan's `Documentation impact` is updated; a change to an integration, a flow, a security rule, a data store or a component boundary without the matching page update is a **major** finding, even when the plan said `none`. Pages follow the rules of the `architecture-mapping` skill (sourced statements, valid Mermaid, no secrets). Changes without architectural effect (wording, labels, styles, translations, tests only, internal refactoring) need no update: do not report them.
4. **Quality:** correctness first (logic, edge cases, error handling, concurrency), then security, performance, maintainability and tests, guided by the standards of step 2.
5. **Verify:** run the project's test and lint commands when they exist. A failing test is a blocker, unless it also fails on the base branch.
6. **Classify the findings:**
   - **blocker:** wrong behavior, security issue, data loss, failing tests, acceptance criterion not met;
   - **major:** significant maintainability, performance or robustness problem, or plan violation;
   - **minor:** worth fixing, not blocking.
   Skip nits and style already enforced by linters. Each finding gives a location (`file:line`), the problem, the reason (rule or standard) and a suggested fix.
7. **Verdict:** `APPROVED` when there is no blocker or major finding, otherwise `CHANGES_REQUESTED`.
8. **Write `.ai/<slug>/review.md`** from the [review template](./assets/review-template.md). The front matter must contain `verdict`, `reviewed_sha` (the full HEAD SHA), `base_sha` and `iteration`, which is `review_iterations` from `state.json` (the builder increments it before each run): the workflow hooks check them, and refuse a review with another iteration. Replace the previous review and summarize what changed since the last iteration. Write it with the file edit tools, never from the shell: the hooks only accept a `review.md` written by the reviewer subagent.
9. **Return** a short summary to the builder: verdict, blocker and major findings, and the minor findings to post on the PR.

## Constraints

- Never modify source code, tests, git history or remote state. The only file you write is `review.md` (the hooks deny any other write from the reviewer).
- In a re-review, focus on the new commits and check that the previous blocking findings are resolved, without reopening settled decisions.
- Be concise and specific: a finding without a location and a reason is not actionable.
