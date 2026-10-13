# 0025: Home screen leads with "Up next" + capture; no judgment in the visual language

- **Status:** Accepted
- **Date:** 2026-10-09
- **Deciders:** Tanmay Hatkar

## Context

A design pass over `mobile/` (screenshots in `docs/screenshots/`) checked
the UI against the product's own principles and found it working against
them in a few places:

- Missed commitments were styled as **red "overdue" alarms**, the most
  emphatic thing on screen. That contradicts PRD §5 principle 3 ("recall,
  never judgment") and undermines the stale-plan mechanic: restarting
  should feel free.
- Section chips showed **done/total counts** (`Career · 3/7`). That's a
  completion stat, the category ADR-0023 deleted ("no streak tyranny").
- The core action, telling Overwatch what you'll do, was a small header
  button, while the manual form got the floating `+`. The product's
  differentiator is capture plus talkback, not form entry.
- Nothing on the home screen answered "what should I start right now?",
  which is the "helps you start" half of the positioning.
- Icons were emoji with no accessibility labels, and every row carried an
  always-visible destructive `×`.

## Decision

1. **"Up next" focus card** at the top of the home screen: the soonest open
   commitment in the next 12 hours, with a countdown and the parser's
   reminder line (ADR-0021), plus **Done / Move it / talk in chat**. If
   nothing is upcoming, it shows the most recent one that slipped as
   **"Still on?"**, the in-app twin of the stale-plan check-in.
2. **No judgment colours.** Passed commitments read **"from earlier"** in a
   neutral amber; the section is titled "From earlier". Red is reserved for
   destructive actions (delete, sign out).
3. **No completion counts** on section chips.
4. **Capture first.** A persistent bottom bar, "Tell Overwatch what you'll
   do…", opens chat. Manual add is the secondary `+` beside it.
5. **Brief and reflection end in a next step** ("Plan the day in chat",
   "Renegotiate in chat"), since that's where planning happens.
6. **Icons** use `@react-native-vector-icons/ionicons` (dynamic font
   loading via `expo-font`). Expo's docs mark `@expo/vector-icons`
   deprecated. Every icon-only control gets an accessibility label.
7. **Delete moves into the edit sheet**, off the list rows.

## Alternatives considered

- **Keep red, soften the copy only.** Rejected: colour carries the
  judgment more than the words do.
- **Make the home screen the chat.** Rejected for now: the list is what
  the widget and "at a glance" use rely on. A capture bar gets most of the
  benefit without losing the list.
- **`@expo/vector-icons`.** Rejected because it's deprecated in current Expo docs.

## Consequences

### Positive

- The first screen answers "what now?" and makes restarting a slipped plan
  one tap.
- The visuals now agree with PRD §5, so there's one less thing quietly
  contradicting the product.
- Better accessibility (labelled controls, real icons).

### Negative

- The up-next commitment also appears in its list section (deliberate: the
  card is a lens, not a move).
- A new dependency (`@react-native-vector-icons/ionicons`) needs a fresh dev
  build to bundle its font natively. Its config plugin was added to
  `app.json`.

## References

- PRD §5 (principles), ADR-0017 (stale check), ADR-0021 (reminder phrasing),
  ADR-0023 (no stats/streaks), ADR-0024 (mobile-only)
