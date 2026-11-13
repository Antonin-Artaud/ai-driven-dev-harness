# UI checklist

Use when no project UI or accessibility skill covers the topic. Check only what the lot touches.

## Accessibility (WCAG 2.1 AA)
- Native semantic elements first (`button`, `a`, `label`, headings in order, lists, landmarks); ARIA only to fill a gap.
- Every control has an accessible name; form fields have visible labels, and errors are tied to their field and announced.
- Everything works with the keyboard; focus is visible; focus order follows the reading order; dialogs trap and restore focus; `Escape` closes them.
- Contrast: 4.5:1 for text, 3:1 for large text, icons and control boundaries.
- Targets at least 24×24 CSS px (44×44 on touch-first screens when the project says so).
- No information conveyed by colour, position or sound only; images have alternatives or are decorative.
- Respects `prefers-reduced-motion`; nothing flashes more than 3 times per second.
- Zoom to 200% and reflow at 320 CSS px without loss of content or function.

## States
- Loading (skeleton or indicator, no layout jump), empty (explains and offers the next action), error (says what happened and how to recover), success, disabled (explains why when it is not obvious), partial and long content, offline or slow network where relevant.

## Consistency
- Uses the project's tokens and components; spacing, typography and colours come from the design system.
- Interaction patterns match similar screens of the product.

## Copy and i18n
- Strings go through the project's translation mechanism; no concatenated sentences; plural and date or number formats follow the locale.
- Labels and messages are short, specific and actionable.

## Performance of the UI
- No layout shift from late content; images sized; long lists virtualized or paginated when the volumes require it.
