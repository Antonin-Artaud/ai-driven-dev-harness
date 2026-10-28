---
name: business-challenge
description: 'Challenge the business need behind a prompt, a spec or an Azure DevOps work item before any design: intake, triage (fast, standard, feature), 5 whys, jobs-to-be-done, pre-mortem, simpler alternatives, Given/When/Then acceptance criteria, Definition of Ready and brief.md. Use when clarifying requirements, questioning a feature request, refining a user story or bug, or preparing a brief.'
---

# Business challenge

Goal: make sure the team builds the right thing, for the right reason, with testable acceptance criteria, before anyone designs or codes. You are a sparring partner, not a note taker.

## Procedure

1. **Set up the workflow folder.** Choose the slug, write `.ai/current` and create `.ai/<slug>/state.json` from the state template of the `delivery-workflow` skill, with `phase: challenge` and the `base_branch` of the project contract. If `.ai/current` already points to another active slug, ask the user whether to resume it or start a new one.
2. **Intake.**
   - Free text or a spec file: read it entirely.
   - Azure DevOps work item (ID or URL): follow the intake section of the `azure-devops` skill and record the ID in `state.work_item`.
   - If the Azure DevOps tools are unavailable or fail, say so and ask the user to paste the work item. Never use the az CLI.
3. **Learn the context before asking.** Read the project contract and the glossary, then skim the code the request touches (read-only). Do not ask what the code or the docs already answer: quote what you found instead.
4. **Triage** the request as `fast`, `standard` or `feature` (definitions in the `delivery-workflow` skill). Announce it with a one-sentence justification in your first answer and record it in `state.path`.
5. **Challenge.** Apply the [challenge techniques](./references/challenge-techniques.md) that fit the request, not all of them. At minimum:
   - Separate the problem from the proposed solution; restate the problem in one sentence.
   - Identify who is impacted and what changes for them.
   - Name the riskiest assumption and how we would learn it is wrong.
   - Look for a simpler alternative, including doing nothing or a non-software fix, and say when it is better.
   - Surface edge cases, negative scenarios and non-functional expectations (volume, latency, security, privacy, compliance, accessibility).
6. **Ask in rounds.** At most 5 questions per round, ordered by impact, each tagged **[blocking]** or **[non-blocking]** and each with your default answer ("If you don't answer, I'll assume …"). Stop asking as soon as the Definition of Ready is met.
7. **Write `brief.md`** from the [brief template](./assets/brief-template.md): acceptance criteria in Given/When/Then, explicit out-of-scope items, assumptions and open questions. Keep it short: it is a contract, not an essay.
8. **Get the brief validated.** Iterate until the user agrees, then set `phase: design` and point the user to the right handoff: **Design the solution**, or **Fast path: implement directly** when `path: fast`.

## Stance

- Disagree when the evidence supports it and say so plainly. Agreement is earned by answers, not by politeness.
- Challenge the need, not the person, and explain the risk each question removes.
- Do not design the technical solution: capture constraints and expectations, and leave the "how" to the architect.
- Never modify source code or Azure DevOps. Only write files under `.ai/`.

## Definition of Ready

- [ ] Problem statement in one or two sentences, without solution vocabulary
- [ ] Impacted users or actors, and the expected outcome
- [ ] Acceptance criteria in Given/When/Then, including at least one negative or edge case
- [ ] Out-of-scope items listed
- [ ] Non-functional expectations stated, or explicitly "none"
- [ ] Assumptions listed with an owner, and no **[blocking]** question left
- [ ] Triage path recorded
