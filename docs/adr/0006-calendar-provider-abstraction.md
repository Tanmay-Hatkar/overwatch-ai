# 0006: Calendar provider abstraction with auto-detection

- **Status:** Accepted
- **Date:** 2026-06-02
- **Deciders:** Tanmay Hatkar

## Context

Slice 7 adds calendar reading to Overwatch. The PRD already named the
goal: a unified day view that ingests events from external calendars
(Google, Outlook, Apple) and shows them alongside commitments. The
strategic decision (see earlier session notes) was that we build a
calendar VIEW, not a calendar engine — we read from external sources
but don't manage event creation/editing/recurrence ourselves.

Two engineering questions to answer:

1. **How do we make the codebase open to adding new sources later
   (Outlook, Apple) without rewriting?**

2. **What's the UX during development, before the user has set up
   OAuth and granted Google access?** The app needs to render something
   useful for the calendar view; an empty grid is unhelpful.

## Decision

**Abstract `CalendarProvider` base class with concrete implementations,
auto-detected at startup.**

The abstraction:

```python
class CalendarProvider(ABC):
    source_name: str

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def list_events_for_date(self, target_date: date) -> list[CalendarEvent]: ...

    @abstractmethod
    def list_events_for_range(
        self, start_date: date, end_date: date
    ) -> list[CalendarEvent]: ...
```

Three concrete implementations:

- **`MockCalendarProvider`** — deterministic fake events (standup,
  lunch, 1:1 on weekdays). Used in dev before OAuth is set up, and in
  every test by default.
- **`GoogleCalendarProvider`** — real Google Calendar API. Loads
  credentials from `token.json` + `credentials.json`, auto-refreshes
  expired tokens, extracts meeting URLs from `hangoutLink`,
  `conferenceData.entryPoints[]`, and regex scan of description/location.
- **`GoogleCalendarProvider` (unconfigured)** — when token files are
  missing, `is_configured()` returns False and we transparently fall back
  to the mock.

Auto-detection at startup (in `routes/calendar.py`):

```python
def _select_provider() -> CalendarProvider:
    google = GoogleCalendarProvider()
    if google.is_configured():
        return google
    return MockCalendarProvider()
```

The `CalendarService` wraps whichever provider was selected with
defensive error handling: any exception during fetch returns an empty
list rather than propagating. Calendar context is supplementary; the
rest of the app keeps working even if Google has a hiccup.

## Alternatives considered

### Single Google provider, no abstraction

The simplest possible structure. One concrete file, no inheritance,
no factory.

**Rejected because:**
- Slice 7b (multi-account) and beyond (Outlook, Apple) become real
  refactors instead of additions
- Tests would need real Google credentials or extensive monkey-patching
- Cannot ship a usable demo without OAuth setup

### Use a library like `caldav` or `python-o365`

There are libraries that already abstract over multiple calendar APIs.

**Rejected because:**
- Each adds a dependency for capability we don't yet need
- Their abstractions don't quite match ours (event creation, recurrence
  handling, etc. — things we explicitly decided NOT to do)
- Our `CalendarEvent` model is opinionated about which fields we surface;
  a library's model would force us to reshape on every call
- We can always adopt one later for a specific provider if it saves
  significant work

### Configuration-driven provider selection (`CALENDAR_PROVIDER=google`)

Have an env var explicitly select the provider rather than
auto-detecting from file presence.

**Rejected because:**
- One more thing to remember to configure
- The "token.json exists ↔ Google is wired up" relationship is implicit
  but reliable
- For multi-account (slice 7b), we'll need a settings UI anyway; that's
  the natural moment to introduce explicit selection

### Inheritance hierarchy with shared base class behavior

Put HTTP retry, caching, etc. into an abstract base that concrete
providers inherit.

**Rejected because:**
- Premature for two providers
- HTTP/auth differs significantly between Google (OAuth + discovery
  service) and Outlook (Microsoft Graph + different flow) and CalDAV
  (entirely different protocol)
- Composition (CalendarService wrapping a provider) gives us the
  cross-cutting concerns we need (defensive errors, sorting) without
  forcing providers to share more than the interface

## Consequences

### Positive

- **Adding Outlook = one new file.** Same interface, different
  implementation. No changes to service, routes, UI, or tests.
- **Development works without OAuth.** A new contributor (or
  future-you on a new machine) sees realistic data immediately. They
  set up Google when ready, not as a prerequisite to running the app.
- **Tests don't need real Google credentials.** Every existing test
  uses MockCalendarProvider; tests specifically for
  GoogleCalendarProvider mock the Google API client library.
- **Token rotation is invisible to callers.** Refresh logic lives in
  one place (the Google provider) and persists back to disk so subsequent
  invocations skip the refresh.
- **Defensive errors keep the rest of the app working.** A Google
  outage means an empty event list, not a 500 on the briefing endpoint.

### Negative

- **The mock is decoration, not behavior.** Tests that use mock data
  can't verify edge cases that only happen with real Google quirks
  (timezone normalizations, weird description encoding, etc.). We add
  Google-specific unit tests for these.
- **Auto-detection is silent.** A user who copies an empty `token.json`
  by mistake gets the Google provider returning empty rather than the
  mock returning realistic data — possibly confusing during debugging.
  Mitigated by the startup log line that names the active provider.
- **Single-provider assumption today.** `CalendarService` holds one
  provider. Multi-source aggregation (work Google + personal Google +
  Outlook) needs slice 7b — a list of providers and merged sorting.

### Future considerations

- Slice 7b: a list of providers, possibly settings-driven, with a
  UI to manage connected accounts
- Slice 7c: `OutlookCalendarProvider` via Microsoft Graph
- Slice 7d: `AppleCalendarProvider` via CalDAV (different protocol;
  the interface still applies)
- The `MockCalendarProvider` could grow a "scenario" parameter (busy
  day, empty day, lots of overdue) for richer manual UX testing

## References

- v1's `integrations/google_calendar.py` — the procedural predecessor,
  kept as reference for the timezone + token refresh quirks
- ADR-0001 (vertical slicing methodology) — why this slice scopes
  narrowly
- `backend/app/providers/calendar_provider.py` — the abstract base
- `backend/app/providers/mock_calendar_provider.py` — dev/test default
- `backend/app/providers/google_calendar_provider.py` — real impl
- `backend/app/routes/calendar.py` — auto-detection logic
- `backend/scripts/setup_google_oauth.py` — one-time OAuth setup flow
