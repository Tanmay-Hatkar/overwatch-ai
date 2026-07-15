# Product Requirements Document — Overwatch

**Status:** Draft (active development)
**Last updated:** 2026-05-12
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

### In scope for v1 (MVP)

- Personal-use system for the author
- Single user (no multi-tenancy)
- Google Calendar integration (read-only initially; later write)
- Local + cloud LLM via fallback chain (OpenAI → Groq → Ollama)
- Conversational input (text first; voice as augmentation)
- Commitment capture + surgical follow-up
- Morning brief, evening reflection
- Rate-goal tracking
- Stale plan detection

### Out of scope for v1

- Multi-user / multi-tenant
- Auth / accounts
- Multiple calendar providers (Outlook, Apple)
- Mobile app
- Public sharing / SaaS
- Production deployment beyond personal use
- Advanced analytics / insights

### Maybe later

- Outlook / Apple calendar via abstraction
- TTS for voice output
- Long-term pattern recognition over months of data
- Desktop notifications / system tray
- Mobile companion

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
