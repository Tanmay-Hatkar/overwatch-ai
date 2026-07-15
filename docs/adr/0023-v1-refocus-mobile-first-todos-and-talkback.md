# 0023: v1 refocus — mobile-first, Todos + proactive talkback, cut the rest

- **Status:** Accepted
- **Date:** 2026-07-15
- **Deciders:** Tanmay Hatkar

Note on numbering: ADR-0021 (reminder-phrasing) exists on the still-open
`feat/reminder-phrasing` branch (PR #6) but hasn't merged to `main` as of
this ADR, so `main`'s ADR sequence currently has a gap at 0021. This ADR
takes 0023 to avoid a collision when that PR lands.

## Context

Two conversations drove this. First, a walk through "what's actually
useful here from a business/marketing perspective" (ADR-0022) concluded
the calendar grid actively worked against the product's own positioning.
Second, and bigger: a direct reassessment of the project's purpose. The
original motivation wasn't "track my commitments" in the abstract — it was
wanting something that pulls the author back from unproductive distraction
(Instagram, specifically) toward the work that actually matters for their
career, framed gently rather than as another guilt-inducing habit tracker.

That reassessment surfaced a real fork: building a system that reacts to
*distraction* (detecting a distracting app in the foreground and
intervening in the moment) is a fundamentally different, heavier build
than the clock/staleness-triggered talkback that already exists — it
needs OS-level usage-monitoring permissions (Android `UsageStatsManager`,
iOS Screen Time/Family Controls) that are hard to get approved and don't
exist yet in this codebase at all. Decided to shelve that for now rather
than block the whole refocus on it (see PRD §9, "Deferred").

What's left, once that's set aside, turned out to already be most of what
the app does: **write down what you're doing today (a Todos list, timed or
not) and get proactively talked back to about it** — morning brief,
evening reflection, exactly-timed reminders, a one-time stale-plan
check-in, escalation if ignored. A competitive pass (see conversation
record; not reproduced here) confirmed natural-language capture and even
relentless reminders are no longer novel on their own — Todoist, Due,
Sunsama, Composed all do pieces of this now. What's still differentiated:
a stale-plan check-in that fires once, resolves conversationally, and
costs nothing either way — positioned between plain to-do apps (too soft)
and financial-stakes commitment-device apps like Beeminder/TaskRatchet
(effective, but punitive). That's the mechanic worth protecting; everything
else gets evaluated against whether it serves it.

Separately, the author confirmed the product is mobile-first — "I cannot
imagine someone using this on their desktop" — even though a decent amount
of the existing frontend (the 70vw desktop-width container, hover-first
interaction patterns) was built assuming a browser tab on a monitor.

Also on the table, not yet decided: whether this eventually becomes a
public product other students/strugglers can install, versus staying a
personal tool the author open-sources or keeps private. Multi-tenancy
(ADR-0013) already exists for this, unused. Deliberately deferred here —
see PRD §9 — because "works for me" and "works for strangers whose LLM
calls I'm paying for" are different projects that happen to share code.

## Decision

**Cut, permanently (not "hidden," removed):**

1. **Groups/sections** (`group_name` field, group UI in `CommitmentList.jsx`)
   and **manual reschedule-from-list**. Both are list-management ceremony —
   exactly the "every task is a form" friction PRD §3 calls out in other
   apps. Neither serves the capture → talkback loop.
2. **The stats/streaks feature** (`StatsBar.jsx`, `stats_service.py`,
   `GET /stats/today`, streak-day computation). Built, never actually
   shipped to the running UI, and a direct contradiction of PRD principle
   #3 ("no streak tyranny") if it ever were. Deleted outright rather than
   left dormant — dormant-but-contradicts-the-PRD is worse than absent.
3. **The structured commitment form** (`CommitmentForm.jsx`) and the
   standalone **notification-permission nudge** (`NotificationStatus.jsx`).
   Both dormant, both superseded (chat capture; Settings' permission
   status), no reason to keep unused code that has to be reasoned about
   during future refactors.

Calendar UI removal is already covered by ADR-0022 and not re-litigated
here.

**Committed, going forward:**

4. **Mobile-first is not aspirational, it's the design default.** The web
   SPA's shell gets rebuilt mobile-width-first (no 70vw desktop cap as the
   baseline); the native Android app is the primary target platform for
   verification, not a secondary check.
5. **The morning brief becomes a genuine planning prompt when the day is
   empty**, not only a read-out of whatever's already captured — closing
   the gap between "plan your day as a list" (what the author actually
   wants) and what the brief currently does (summarize silence).

**Deferred, not decided against:** public multi-user hosting, and
usage-aware (app-detection) proactive intervention. Both real, both
explicitly out of this v1. See PRD §9.

## Alternatives considered

- **Keep the dormant components hidden instead of deleting them**, in case
  "maybe later." Rejected for the stats/streaks case specifically — it
  contradicts a stated product principle, so "later" isn't neutral, it's a
  standing risk of accidentally re-enabling something the product
  explicitly rejects. Rejected for the other two on ordinary
  dead-code-maintenance grounds — nothing about them is hard to rebuild if
  actually needed later, and `git log` remembers them regardless.
- **Build the usage-aware distraction detector now, since it's the actual
  original motivation.** Rejected for v1 — real platform-permission cost
  (Android Usage Access grant flow, iOS Screen Time entitlement is
  effectively gated to parental-control-category apps), and the
  clock/staleness-triggered version already covers most of the "pull me
  back to what I said I'd do" value at a fraction of the engineering and
  approval risk.
- **Decide the public-product question now**, since "novel idea, want to
  put it out there" was explicitly raised. Rejected for v1 — it changes
  architecture decisions (cost controls, OAuth verification, distribution)
  that shouldn't be made speculatively before the trimmed core loop is
  even validated solo.

## Consequences

### Positive

- Every remaining feature maps directly to either "Todos" (capture + list)
  or "talkback" (the proactive USP) — nothing left that requires a
  separate justification.
- Removes a live contradiction of the product's own stated principles
  (streaks) instead of leaving it dormant and re-enable-able by accident.
- Mobile-first stops being an afterthought applied to a desktop-shaped
  frontend and becomes the actual design constraint.
- Smaller surface area to test, maintain, and reason about going into the
  next build phase.

### Negative

- Groups/sections and reschedule-from-list are real, working features
  someone might miss. No usage data says they matter (single-author v1) —
  flagged here in case that changes.
- The public-product and distraction-detection questions remain genuinely
  open. This ADR narrows scope but doesn't resolve either — both will need
  their own decision (and likely their own ADR) later.
- Rebuilding the frontend shell mobile-first touches code well outside the
  strict "remove X" diff — closer to a real (if scoped) redesign, more risk
  than a pure deletion pass.

### Future considerations

- If groups/reschedule turn out to be missed, re-add scoped to what's
  actually needed, not the general-purpose version being removed now.
- Revisit usage-aware intervention once the clock-based loop is validated
  and the OS permission cost feels worth paying.
- Revisit public hosting once solo usage validates the core loop (PRD §10
  success criteria) — at that point, cost model and OAuth verification
  need their own design pass.

## References

- `docs/PRD.md` §6, §9 (updated alongside this ADR)
- ADR-0013 — multi-tenancy / user scoping (dormant, deferred here)
- ADR-0017 — stale-plan detection (the mechanic this refocus protects)
- ADR-0019 — ring-alarm escalation
- ADR-0020 — home-screen widget
- ADR-0022 — demote calendar to background context (companion decision)
- `frontend/src/components/StatsBar.jsx`, `CommitmentForm.jsx`,
  `NotificationStatus.jsx` — removed by this decision
- `backend/app/services/stats_service.py`, `backend/app/routes/stats.py` —
  removed by this decision
