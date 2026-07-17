# 0022: Demote the calendar grid from primary UI to background context

- **Status:** Accepted
- **Date:** 2026-07-15
- **Deciders:** Tanmay Hatkar

## Context

Between ADR-0006 (calendar provider abstraction) and `aa34fad` (full
12am-12am day grid with scroll-to-now), the home screen grew a full weekly
calendar view — a "This Week" hero card with a Google-Calendar-style time
grid, a prominent "Connect Google Calendar" banner, and connect/disconnect
controls — sitting above the commitment list.

This drifted against the PRD, which says explicitly (section 7, "What it
is NOT"): *"Not a calendar — Google Calendar exists, we read from it."*
The ICP (section 6) is "strugglers, not optimizers" — someone who writes a
to-do list and stops looking at it by 11am — not someone who wants another
day-planner grid to manage. A calendar-grid hero:

- Puts Overwatch in direct visual competition with Google Calendar,
  Fantastical, and Motion — a fight it cannot win by being "another
  calendar."
- Buries the actual novel mechanic (natural-language commitment capture +
  surgical, exactly-timed follow-up) below a UI element that looks like
  every other productivity app.
- Signals "optimizer tooling" to a "struggler" audience, undercutting the
  positioning.

Revisited now as part of a deliberate product-focus pass: keep the home
screen centered on commitments (the "Todos" of the app) and the
differentiated mechanics — reminder phrasing, ring-alarm escalation,
stale-plan check-ins, voice, the home-screen widget — and stop marketing
(and building UI around) the calendar as a feature.

## Decision

Remove the weekly calendar grid (`WeeklyCalendar.jsx`) from the home
screen entirely. `App.jsx` now renders: briefing → reflection →
commitment list → push setup, with no calendar view.

Google Calendar integration is **not removed** — `briefing_service.py`
still reads today's events (`CalendarService.list_today`) to give the
morning briefing schedule-aware context (e.g. "you have a 2pm meeting, so
1:30 might be tight"). This is backend plumbing, not a screen.

Connect/disconnect moves to Settings as a single status line
(`CalendarConnection.jsx`) — one sentence explaining it's optional context
for the briefing, a "Connected" chip, and a disconnect action. No event
list, no grid, no "This Week" hero.

`GET /calendar/week` and its frontend caller (`getWeekEvents`) are left in
the backend (still exercised by `test_calendar_routes.py`) but the
frontend export was deleted as dead code — nothing in `src/` calls it
anymore. `GET /calendar/today` is what the briefing actually uses.

## Alternatives considered

- **Keep the grid, just make it smaller/collapsed by default.** Rejected —
  a de-emphasized calendar is still a calendar; it still says "this is a
  calendar app" the moment someone expands it, and still cost UI real
  estate and maintenance for a screen the PRD says shouldn't exist.
- **Remove Google Calendar integration entirely** (delete the OAuth flow,
  provider, routes). Rejected — the read-only integration earns its keep
  as *briefing* context (a real, if minor, differentiator: the follow-up
  can be schedule-aware). The problem was never the integration; it was
  giving it a whole screen.
- **Keep it as an opt-in "Calendar" tab/view.** Rejected for v1 — adds
  navigation complexity (tabs/routes) for a feature explicitly out of
  scope of the pitch. Revisit only if a future user segment actually asks
  for a calendar view.

## Consequences

### Positive

- Home screen is now: briefing, reflection, commitments, chat — nothing
  that looks like a competitor's product. Every pixel supports the "your
  stated commitments, followed up on" pitch.
- Less frontend surface to maintain (one fewer 460-line component, one
  fewer polling effect, one fewer skeleton state).
- Settings still gives power users the option to connect Calendar for
  richer briefings, without it competing for home-screen attention.

### Negative

- Users who *did* like glancing at events alongside commitments lose that
  view. No current usage data suggests this matters (personal-use v1,
  single author) — flagged here in case it resurfaces as real feedback.
- `GET /calendar/week` is now backend-only dead weight from the frontend's
  perspective (still tested, still reachable, just unused by the SPA). Not
  removed because deleting a working, tested endpoint on a hunch is worse
  than leaving an honest unused-but-functional one; revisit if it's still
  unused in a future cleanup pass.

### Future considerations

- If Overwatch ever needs a calendar view again, it should be scoped as a
  deliberate, opt-in secondary screen — not the home-screen default — and
  come with a PRD update justifying the reversal of this decision.

## References

- `docs/PRD.md` §6 (ICP), §7 ("What it is NOT")
- ADR-0006 — calendar provider abstraction
- `frontend/src/App.jsx` — home screen composition
- `frontend/src/components/CalendarConnection.jsx` — new Settings-only control
- `backend/app/services/briefing_service.py` — the one remaining consumer of calendar data
