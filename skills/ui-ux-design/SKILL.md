---
name: ui-ux-design
description: 'UI lot procedure of the ai-driven-dev-harness, for the ui-ux-designer subagent: implement one lot marked Kind ui in .ai/<slug>/plan.md, starting from the project''s design system, components and tokens, with WCAG 2.1 AA accessibility, responsive behaviour, every state designed (loading, empty, error, success, disabled), the project''s UX copy and i18n conventions, tests and visual evidence. Use only within this delivery workflow, when the builder delegates a UI lot.'
---

# UI and UX design

You implement one UI lot of a validated plan, like the implementer, with a designer's standards. Follow the implementer procedure and the lot report of the `plan-execution` skill (one lot, one commit, no unrelated refactoring, `PLAN DEVIATION` when the plan is wrong); this skill adds the UI rules.

## Procedure

1. **Read the intent.** The lot, the **UX intent** section of `brief.md` and `plan.md` (users, tasks, key screens and states), and the project instructions for the UI files you touch. Do not invent the intent: if a screen or a state is not specified and matters, report a `PLAN DEVIATION` with your proposal.
2. **Start from what exists.** Find the project's design system, component library, tokens (colours, spacing, typography), layout patterns and similar screens; reuse them. A new component only when no existing one fits, built from the same tokens. No new UI dependency unless the plan gives the reason.
3. **Design every state** the lot touches: loading, empty, error (with a way out), success, disabled, partial data, long content, slow network.
4. **Accessibility (WCAG 2.1 AA)** with the [UI checklist](./references/ui-checklist.md): semantic elements, labels and names, keyboard operation and visible focus, focus order and management in dialogs, contrast, target sizes, no information by colour only, reduced motion.
5. **Responsive behaviour** on the breakpoints the project supports; no horizontal scroll at 320 CSS px for content pages.
6. **Copy and i18n.** Follow the project's UX copy conventions and translation mechanism: no hard-coded user-facing strings where the project translates them; clear, actionable error messages.
7. **Tests first where UI logic is testable** (state handling, validation, formatting, accessibility queries): write the failing test, then the code. Run the project's build, lint and test commands.
8. **Visual evidence.** When the project contract gives a preview, story or screenshot command, run it and list the screenshots or stories in the lot report (paths, states covered). Otherwise say "no visual evidence: <reason>" in the report.
9. Commit once and return the lot report of the `plan-execution` skill, plus: components reused or created, states covered, accessibility checks done, visual evidence.

## Constraints

- Never write under `.ai/` and never push (the hooks deny `.ai/` writes).
- Only the tasks of your lot; no redesign of screens the plan does not touch.
