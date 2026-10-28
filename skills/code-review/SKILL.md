---
name: code-review
description: 'Independent code review of a work branch (merge-base..HEAD) against brief.md, plan.md and the project''s own review skills and instructions, with baseline correctness, security, performance, maintainability and test checklists as fallback. Writes review.md with severity-ranked findings, a verdict and the reviewed commit SHA. Use when reviewing code, checking plan and acceptance criteria conformance, or re-reviewing fixes.'
---

# Code review

You are independent from the implementer: verify in the code, never trust summaries.

## Procedure

1. **Scope.** Read `.ai/current`, `state.json`, `brief.md` and `plan.md`. Compute `base_sha` with `git merge-base HEAD origin/<base_branch>` (fall back to `<base_branch>`) and `head_sha` with `git rev-parse HEAD`. Review `git diff <base_sha>..HEAD` and `git log <base_sha>..HEAD`.
2. **Standards**, following the skill precedence of the `delivery-workflow` skill: skills mapped to the review stage in the project contract, then project skills whose description matches the changed files or topics, then the instructions whose `applyTo` matches the changed files. Use the [baseline checklist](./references/baseline-checklist.md) only for topics no project standard covers. List every standard you applied.
3. **Conformance.**
   - Every lot and task of the plan is implemented; nothing outside the plan (scope creep) unless it is listed as a deviation.
   - Every acceptance criterion is covered by at least one meaningful test.
   - The decisions of the plan's ADR are respected.
4. **Quality:** correctness first (logic, edge cases, error handling, concurrency), then security, performance, maintainability and tests, guided by the standards of step 2.
5. **Verify:** run the project's test and lint commands when they exist. A failing test is a blocker, unless it also fails on the base branch.
6. **Classify the findings:**
   - **blocker:** wrong behavior, security issue, data loss, failing tests, acceptance criterion not met;
   - **major:** significant maintainability, performance or robustness problem, or plan violation;
   - **minor:** worth fixing, not blocking.
   Skip nits and style already enforced by linters. Each finding gives a location (`file:line`), the problem, the reason (rule or standard) and a suggested fix.
7. **Verdict:** `APPROVED` when there is no blocker or major finding, otherwise `CHANGES_REQUESTED`.
8. **Write `.ai/<slug>/review.md`** from the [review template](./assets/review-template.md). The front matter must contain `verdict`, `reviewed_sha` (the full HEAD SHA), `base_sha` and `iteration`: the workflow hooks read them. Replace the previous review and summarize what changed since the last iteration.
9. **Return** a short summary to the builder: verdict, blocker and major findings, and the minor findings to post on the PR.

## Constraints

- Never modify source code, tests, git history or remote state. The only file you write is `review.md`.
- In a re-review, focus on the new commits and check that the previous blocking findings are resolved, without reopening settled decisions.
- Be concise and specific: a finding without a location and a reason is not actionable.
