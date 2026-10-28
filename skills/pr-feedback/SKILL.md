---
name: pr-feedback
description: 'Address the comments of an Azure Repos draft pull request: list the active threads, triage them (fix, discuss, decline) for the user to validate, delegate the fixes to the implementer, re-review, push, then reply to each thread with the fix commit. Use when handling PR review comments or reviewer feedback, or after the "Address PR feedback" handoff.'
---

# PR feedback

## Procedure

1. **Locate the PR.** Read `.ai/current` and `state.json` (`pull_request`, `branch`). Check out the work branch and update it from `origin/<branch>`. Set `phase: feedback` and `review_iterations: 0`.
2. **Collect the threads** with the `ado-read` tools: `repo_pull_request_thread` `list`, then `list_comments` when needed. Keep the active threads with human or AI comments; ignore system threads (votes, iterations, status changes) and closed or resolved ones.
3. **Triage** each thread in `feedback.md` with the [feedback template](./assets/feedback-template.md):
   - **fix:** valid and in scope; describe the intended change;
   - **discuss:** ambiguous, conflicting or out of scope; draft the reply or the question;
   - **decline:** you disagree; give the reason (brief, plan or standard).
   Mark each thread's origin: **AI** when its first comment starts with `🤖`, otherwise **human**.
4. **Stop and ask the user to validate the triage.** Do not change any code before they confirm or amend it. Nothing has changed since the last approved review, so the review gate lets you stop.
5. **Fix:** send the validated **fix** items to an `implementer` run as one feedback lot, with the architecture pages they affect, (several lots only for large, unrelated fixes). Then run the `reviewer` subagent on the new commits and increment `review_iterations`; the loop limit of the `plan-execution` skill applies.
6. **Push** with `git push` (the user confirms; never force push).
7. **Reply on every triaged thread** with `repo_pull_request_thread_write` `reply`. The content always starts with `🤖`:
   - fix: `🤖 Fixed in <sha7>: <what changed>`
   - discuss: `🤖 <question or proposal>`
   - decline: `🤖 Not changed: <reason>`
   Set the status to `Fixed` only on the AI threads you fixed. Never resolve, close or change the status of a human thread: its author does it.
8. **Update the PR description** if the scope or the decisions changed (`repo_pull_request_write` `update` with `description` only, at most 4000 characters).
9. Set `phase: pr-open` and report the fixed, discussed and declined threads, the commits and the review verdict.
