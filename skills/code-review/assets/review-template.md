---
verdict: CHANGES_REQUESTED
reviewed_sha: <full HEAD sha>
base_sha: <full merge-base sha>
iteration: 1
---
# Review — <title>

## Summary
<Two or three sentences: overall assessment and reason for the verdict.>

## Standards applied
- <project skill, instruction or baseline checklist section>

## Plan and acceptance criteria conformance
| Item | Status | Evidence |
|---|---|---|
| Lot 1 — … | done / partial / missing | `file:line`, commit |
| AC1 — … | covered / not covered | `test name` |
| Documentation impact | done / missing / not needed | `docs/architecture/...` |

## Findings
| # | Severity | Location | Problem | Why | Suggested fix |
|---|---|---|---|---|---|
| 1 | blocker | `src/x.py:42` | … | … | … |

## Verification
- `<command>` → <result>
- Mutation testing (<gate | report | off>): `<command>` → <summary of the gate script: score of the changed lines, threshold, survivors> | off: <reason>

## Since the previous iteration
<Resolved and still open findings, or "first review".>
