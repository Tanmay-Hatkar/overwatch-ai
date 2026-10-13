# 0026: Weekly rate goals as their own entity, with a once-a-week check-in

- **Status:** Accepted
- **Date:** 2026-10-13
- **Deciders:** Tanmay Hatkar

## Context

PRD §4.4 promises rate goals ("10 applications a week", "gym 4× weekly"),
and §9 lists them as in scope for v1. Nothing implemented them. For the
ICP (job seekers, students), this is the most common shape a plan takes:
the commitment isn't "do X at 2:30", it's "do X enough times this week".
Squeezing it into a one-off todo ("Apply to 10 jobs") gives a single
checkbox that only closes on the tenth application, so it can't be
ticked off as the work actually happens.

A quick look at how others do it:

- **Habitify** sets a number of days per week, but layers streaks on top
  (a weekly streak continues while the weekly target is met).
- **Beeminder** averages a weekly rate into a daily pace with a "safety
  buffer". It works because it charges money when you fall behind. That
  punitive tone is exactly what PRD §6 positions against.
- **Coach.me** has weekly targets, but its streaks only count consecutive
  days, which makes them confusing.

So the useful part is a weekly count plus a sense of how much is left.
The part to leave out is streaks, debt and carryover.

PRD §11 also left an open question: does "a week" mean Mon–Fri, the
calendar week, or a sliding 7 days?

## Decision

1. **Separate entity, not a commitment field.** New `goals` table (text,
   target_count, status, decision, decision_week) and a `goal_logs` table
   (amount, logged_at). Commitments keep their time-based lifecycle
   (due_at, reminders, stale checks, ring alarms). A rate goal has none of
   that, and threading `target_count` through all of it would add a branch
   to every one of those paths.
2. **The week is the user's local calendar week, Monday to Sunday.**
   Progress is never stored. It's `SUM(goal_logs.amount)` within
   [Monday 00:00, next Monday 00:00) in the request's timezone, so undo,
   travel, and the weekly reset are all correct by construction. This
   answers PRD §11's cadence question.
3. **No history, no carryover, no streaks.** A new week starts at zero.
   Logs from past weeks stay in the table (undo can't reach them) but
   nothing reads them. This keeps ADR-0023's "no streak tyranny" rule.
4. **One end-of-week check-in, asked once.** From Friday on
   (`GOAL_CHECK_IN_DAYS_LEFT=3`, counting today), an unmet goal is in state
   `check_in`, and the app asks inline: *keep going, adjust the target, or
   call this week good?* Any answer (`keep_going` / `call_it_good`) is
   stored with the week it applies to, and the question doesn't come back
   that week. "Call it good" shows as a choice ("You called this week
   good. Fresh start Monday."), never as a miss. This is PRD §4.5's
   "Friday check", and it's the same mechanic as the stale-plan check-in
   (ADR-0017).
5. **Chat is the main input; +1 is the fallback.** Two new chat intents:
   `add_goal` ("10 applications this week") and `log_goal` ("applied to 2
   more"), resolved against a "Weekly goals" context block by id, the same
   way `modify_commitment` targets commitments. A plan ("I'll apply to 3
   today") stays an `add_commitment`. If a goal intent can't be applied
   (unknown id, unusable count), the LLM's reply is replaced with an
   honest question instead of a false "Logged".
6. **Home screen "This week" section**, under Up next: a count, a thin bar,
   a one-tap +1, and the inline check-in. Tapping a goal opens a sheet to
   rename it, change the target, undo the last +1, or delete it.

## Alternatives considered

- **`target_count` + `period` on commitments.** Rejected: reminders, stale
  checks, roll-forward, ring alarms, the widget and Up next would each need
  a "unless it's a goal" branch. Goals share the *idea* of a commitment
  (PRD §5 "one memory, many shapes") without needing to share the row.
- **Sliding 7-day window.** Rejected: "this week" in conversation means the
  calendar week, and a sliding window never lets a bad week end. It just
  keeps dragging behind you, which is the opposite of the restart-for-free
  feeling the product is going for.
- **Daily pace / "on track" indicator (Beeminder-style).** Rejected for v1:
  "you need 2.3/day to stay on pace" is a judgment in numbers. Showing
  "4 to go · 3 days left" gives the same information and lets the user do
  the math if they want to.
- **Carry unmet counts into next week.** Rejected: that's debt, and debt is
  the streak problem in a different form.
- **Linking todos to goals** (completing "Apply to Shopify" counts toward
  applications). Valuable, but deferred: it needs a way to link items
  (LLM-suggested or manual) and some UI for it. See Future considerations.

## Consequences

### Positive

- The PRD's rate-goal promise exists end to end: chat, API, home screen,
  check-in.
- Logging costs one tap or one sentence, cheaper than forgetting.
- The weekly check-in gives the "renegotiate, don't fail" principle a
  concrete UI.

### Negative

- The chat system prompt grew by ~1k tokens. On Groq's free tier
  (openai/gpt-oss-120b) the full chat prompt already hits the
  tokens-per-minute cap at roughly one message a minute (HTTP 429), and
  this makes it slightly worse. Worth a separate look at prompt size or
  the provider tier.
- `check_in` is time-based but shown only in-app. There's no notification
  for it yet, so a user who doesn't open the app Friday–Sunday won't see it.
- Logs from past weeks accumulate unread. They're tiny and harmless, but
  if a "look back" feature is ever wanted, it must not turn into streaks.

### Future considerations

- A local notification for the check-in (Friday evening), using the same
  client-scheduled approach as the stale check.
- Mention goals in the morning brief / evening reflection prompts.
- Optional todo → goal linking: completing a commitment counts toward a goal.
- Widget support for a goal's count.

## References

- PRD §4.4, §4.5, §5, §11 (cadence question, answered here)
- ADR-0017 (stale-plan check-in, same ask-once mechanic)
- ADR-0023 (no stats/streaks)
- `backend/app/services/goal_service.py`, `backend/migrations/013_goals.sql`
- `mobile/src/components/WeeklyGoals.js`, `mobile/src/lib/goals.js`
- Habitify weekly habits: https://intercom.help/habitify-app/en/articles/9728009-how-to-track-a-weekly-habit
- Beeminder weekly rates: https://help.beeminder.com/article/339-how-do-i-set-a-goal-with-a-weekly-rate
