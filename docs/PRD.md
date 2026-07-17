# Product Requirements Document — Overwatch

**Status:** Draft (active development)
**Last updated:** 2026-07-15 (v1 refocus — see ADR-0023)
**Owner:** Tanmay Hatkar

---

## 1. One-line pitch

A conversational AI that captures the commitments you make to yourself in natural language and surgically reminds you of them — so your plans don't die from neglect.

## 2. The problem

You write a to-do list in the morning. You stop looking at it by 11am. By evening, you've forgotten half of it.

You tell yourself "I'll start interview prep at 2:30." You forget. You start at 4 in a panic.

You say "10 applications this week." By Friday you've done 6. You don't know exactly when you fell off.

The problem isn't *planning*. People plan all the time — on whiteboards, in journals, in conversations with themselves. **The problem is re-engagement.** Plans don't die from being unmade. They die from being forgotten.

## 3. Why current tools fail

- **Calendars are reactive.** They show events when you look at them. They don't pull you back when you don't.
- **To-do apps require ceremony.** Every task is a form: priority, due date, project, tag. Friction in equals nothing in.
- **Habit / streak apps shame you.** "You missed a day" makes things worse. The people who most need help quit the fastest.
- **AI schedulers (Motion, Reclaim) optimize.** Built for executives who already have it together. Not for people who feel behind.
- **Voice assistants (Siri, Pi, ChatGPT) are generic.** They don't know your week, your sprint, your gym split, or your application count.

There's a gap. People make informal commitments to themselves — verbally, in conversation, in passing — and those commitments have nowhere to live.

## 4. The product

A conversational system that:

1. **Captures commitments from natural language.**
   You speak or type the way you'd talk to a friend. The system extracts: what you said, when you said it, when it's due.
   *Example:* "I'll start prep at 2:30." → captures: commitment, `target_time=14:30`, today.

2. **Holds you to your own word.**
   At the moment you committed to, the system surfaces it. Not generic check-ins. Specific recall: *"You said you'd start interview prep at 2:30 — starting?"*

3. **Detects stale plans.**
   If you set a plan and four hours pass with no engagement, the system asks **once**: *"Is the plan still valid, or has the day changed?"* This is the only legitimate proactive interruption.

4. **Tracks rate goals as commitments.**
   "10 applications a week" or "gym 4× weekly" are just commitments with a count and a cadence. Same data model, different shape. Sprint goals, daily targets, fitness frequency — all unified.

5. **Frames recall as agency, not judgment.**
   *"Friday check: 8 applications this week, target was 10. Push 2 to weekend, or call it good?"* — never *"you're 2 behind!"* The framing IS the product.

6. **Bookends the day.**
   Morning brief (today's plan plus past commitments still in flight). End-of-day reflection (what got done, what didn't, what to renegotiate).

## 5. Design principles

1. **EASE in, EASE out.** Low friction to capture commitments. Low friction to ignore the system when needed.
2. **Respectful by default, aggressive on permission.** The system asks before interrupting. User-controlled modes raise or lower its volume.
3. **Recall, never judgment.** Every interaction preserves the user's agency. No shame language. No streak tyranny.
4. **One memory, many shapes.** Sprint goals, day plans, hour commitments, rate goals — same primitive, one conversational interface.
5. **Multi-channel from day 1.** Voice for hands-free moments. Text for normal use. Visual dashboard for at-a-glance. Voice is *one* mode, not the only one.

## 6. Who it's for

**Strugglers, not optimizers.**

Not the executive chasing 10× productivity. The student cramming, the job seeker grinding, the knowledge worker juggling sprints and personal goals. Anyone whose plans die of neglect.

ICP in one sentence: **Someone who writes a to-do list every morning and stops looking at it by 11am.**

**Mobile-first, as of the v1 refocus (ADR-0023).** The struggler this is for
lives on their phone, not at a desk with a browser tab open. The native
Android app (Capacitor-wrapped) is the primary product; the web SPA is the
shell it wraps, not a desktop destination in its own right. Design and
build decisions default to mobile unless a reason is stated.

Positioning note, sharpened after a competitive pass (see ADR-0023): the
gap this fills isn't "no other app reminds you of things" — several do.
It's the combination nobody else has: a stale-plan check-in that asks
**once**, resolved conversationally, with zero penalty either way — sitting
between plain to-do apps (too soft, gets ignored) and financial-stakes
commitment-device apps like Beeminder/TaskRatchet (effective, but punitive,
and wrong tone for someone already struggling).

## 7. What it is NOT

- Not a calendar — Google Calendar exists, we read from it (see ADR-0022:
  the UI briefly grew a full calendar grid on the home screen; it was
  removed to keep this line true. Calendar is background context for the
  morning briefing, not a screen.)
- Not a to-do app — those exist too
- Not Motion / Reclaim — built for executives at peak productivity, wrong audience
- Not Habitica — streaks are tyranny
- Not a voice-only assistant — voice is one channel, not all of them
- Not a coach with fake personality — no manufactured warmth

## 8. The novel mechanic — in one sentence

**The system captures every commitment you make in conversation and follows up at exactly the time you said.**

That's the kernel. Everything else — morning briefs, rate goal tracking, stale plan detection, multi-channel surfacing — flows from there.

## 9. Scope

**Revised 2026-07-15 (ADR-0023).** The original v1 scope below (drafted
2026-05-12) undersold what actually got built — auth, multi-tenancy, and a
native mobile app all shipped before this revision — and included a
calendar-UI direction that turned out to work against the product's own
positioning. This section reflects where the product actually stands and
where it's deliberately headed next, not the original MVP guess.

### In scope for v1

- **Mobile-first.** The native Android app is the primary target; the web
  SPA is mobile-width by default, not a desktop layout.
- Single active user in practice today; auth + multi-tenant data scoping
  exist in the codebase (ADR-0013) but are not exposed as a public product
  yet — see "Deferred," below.
- Local + cloud LLM via fallback chain (OpenAI → Groq → Ollama)
- Conversational input: text and voice, both first-class (voice is no
  longer "augmentation" — native STT/TTS shipped and are load-bearing)
- Commitment capture + surgical, exactly-timed follow-up
- Morning brief, evening reflection — the daily bookending ritual
- Rate-goal tracking with agency-preserving renegotiation
- Stale-plan detection (one-time, conversational, ADR-0017)
- Reminder escalation for ignored reminders (ring alarm, ADR-0019)
- Home-screen widget (ADR-0020)

### Out of scope for v1

- **Calendar as a visible screen.** Google Calendar is read-only
  background context for the morning briefing only — never a UI surface
  again (ADR-0022).
- **List-management ceremony:** groups/sections, manual reschedule-from-list.
  Cut as friction that doesn't serve the core loop (ADR-0023).
- **Completion stats / streaks.** Built, then deliberately removed — direct
  contradiction of principle #3 ("no streak tyranny," §5) if ever shipped
  (ADR-0023).
- Multiple calendar providers (Outlook, Apple) — moot while calendar has no UI
- Desktop as a first-class target
- Production hosting for users other than the author

### Deferred (built or partially built, intentionally not turned on)

- **Public / multi-user hosting.** Multi-tenancy exists at the data layer.
  Turning it into a real product for other strugglers/students is a
  distinct project — LLM cost-per-user, Google OAuth verification for a
  public app, app-store distribution — not a flag flip. Revisit once the
  solo core loop is proven.
- **Usage-aware proactive intervention** (detecting a distracting app in
  the foreground and nudging in the moment, rather than only on a
  clock/staleness trigger). The original motivating idea behind this whole
  refocus — genuinely compelling, genuinely heavier (Android
  `UsageStatsManager` / iOS Screen Time entitlements). Shelved, not
  rejected.

### Maybe later

- Open-source release vs. hosted product, once the "for other users"
  question above is actually being pursued
- Outlook / Apple calendar via abstraction, only if calendar ever becomes a
  feature again
- Long-term pattern recognition over months of data

## 10. Success criteria (for MVP)

- Author uses the app daily for 2+ weeks
- The app surfaces at least one commitment per day that the author would otherwise have forgotten
- The author would feel uncomfortable going back to using a whiteboard instead

## 11. Open questions

- **Cadence parsing for rate goals:** how does the LLM disambiguate "10 apps a week" (Mon-Fri? calendar week? sliding 7 days?)
- **Reconciliation:** if a user mentions a commitment that resembles an existing one, do we update it or create new?
- **Verification:** how does the system know a workout actually happened? (Self-report or integrations?)
- **Privacy:** what data goes to OpenAI vs Ollama? Is there a "sensitive commitment" mode?

These get answered as we hit them in slices.
