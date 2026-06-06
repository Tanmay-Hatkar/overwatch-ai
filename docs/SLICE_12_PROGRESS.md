# Slice 12 — Multi-tenancy: progress checkpoint

**Status:** ~50% complete. Backend is in a half-refactored state — DO NOT
attempt to run tests or start the server until this is finished. Next
session resumes from this doc.

**Branch:** Commit current state to `feature/slice-12-multi-tenancy`.

**Design reference:** [adr/0010-multi-tenancy-row-level-scoping.md](adr/0010-multi-tenancy-row-level-scoping.md)

---

## What's DONE

### Schema
- `migrations/003_multi_tenancy.sql` — adds `user_id` columns to `commitments`, `briefings`, `push_subscriptions`. Backfills if exactly 1 user exists. Rebuilds `briefings` table with `UNIQUE(user_id, date)` instead of `UNIQUE(date)`.
- `migrations/004_google_tokens.sql` — new `google_tokens` table (per-user OAuth tokens, replaces single `token.json`).

### Code (fully migrated)
- `app/repositories/commitment_repository.py` — every method takes `user_id` first; every query scoped.
- `app/services/commitment_service.py` — every method takes `user_id` first; passes to repo.
- `app/services/commitment_parser_service.py` — `parse_and_create(user_id, message)`.
- `app/routes/commitments.py` — every route uses `Depends(current_user)`; passes `user.id`.
- `app/repositories/briefing_repository.py` — `get_for_date(user_id, day)`, `save(user_id, ...)`.
- `app/services/briefing_service.py` — `get_today(user_id, ...)`, `_is_cache_fresh(user_id, ...)`, `_generate_and_save(user_id, ...)`, `_bucket_commitments(user_id, ...)`, `_fetch_events(user_id, ...)`.
- `app/routes/briefings.py` — uses `current_user`, passes `user.id` to service.

---

## What's LEFT (in dependency order)

### 1. CalendarService + GoogleCalendarProvider (per-user OAuth tokens)

This is the **biggest remaining piece** because `GoogleCalendarProvider`
currently reads `token.json` from disk. After this slice, it must load
each user's token from the new `google_tokens` table.

**Steps:**

#### 1a. Create `GoogleTokensRepository`
- New file: `app/repositories/google_tokens_repository.py`
- Methods: `get(user_id)`, `upsert(user_id, credentials_dict)`, `delete(user_id)`
- Stores: access_token, refresh_token, token_uri, client_id, client_secret, scopes, expiry, updated_at

#### 1b. Update `app/providers/google_calendar_provider.py`
- Remove disk-based `token.json` loading from `__init__`
- Add a method like `from_user_token(user_id, repo)` that builds the provider from a DB row
- The existing `list_events_for_range()` logic stays — only the token source changes
- Refresh logic now writes back to the DB instead of `token.json`

#### 1c. Update `app/services/calendar_service.py`
- Methods take `user_id` first
- Internally constructs `GoogleCalendarProvider` per-user via `GoogleTokensRepository`
- If user has no row in `google_tokens`, gracefully return empty events (don't crash)

#### 1d. Update `app/routes/calendar.py`
- Routes use `Depends(current_user)`
- Pass `user.id` to service
- Auto-detection in `_select_provider()` becomes per-user

#### 1e. Add a new route for users to authorize Calendar access
- `GET /calendar/connect/google` — start the Calendar-scope OAuth flow
- `GET /calendar/connect/google/callback` — handle the callback, persist token
- (This is separate from `/auth/google/*` which is the login flow)

### 2. PushService + ReminderScheduler + push routes

#### 2a. `app/repositories/push_subscription_repository.py`
- All methods: add `user_id` parameter, scope queries
- `upsert(user_id, endpoint, p256dh, auth)`
- `list_for_user(user_id)` (replaces `list_all()`)
- `delete_by_endpoint(user_id, endpoint)`

#### 2b. `app/services/push_service.py`
- `broadcast(subscriptions, payload)` — no change to signature, but callers must
  pass user-scoped subscription list

#### 2c. `app/services/reminder_scheduler.py`
- `_tick()` now iterates users:
  ```python
  for user_id in user_repo.list_all_ids():
      due = commitment_repo.list(user_id, status=OPEN)  # filter for due
      subs = push_repo.list_for_user(user_id)
      for c in due_for_first_time:
          push_service.broadcast(subs, payload)
  ```
- `_notified_ids` becomes per-user: `dict[UUID, set[str]]`
- `_is_first_tick` stays global (one-time per scheduler start)

#### 2d. `app/routes/push.py`
- All routes use `Depends(current_user)`
- `subscribe` calls `repo.upsert(user.id, ...)`
- `unsubscribe` calls `repo.delete_by_endpoint(user.id, endpoint)`
- `test` broadcasts only to this user's subscriptions

#### 2e. New `UserRepository.list_all_ids()` method
- Returns `list[UUID]` of every user, for the scheduler to iterate

### 3. StatsService + routes

- `app/services/stats_service.py`: methods take `user_id`
- `app/routes/stats.py`: uses `current_user`, passes `user.id`

### 4. ChatService

- `app/services/chat_service.py`:
  - `handle(user_id, request)` instead of `handle(request)`
  - When fetching commitments + calendar for context, scope by `user_id`
  - When creating a commitment from `add_commitment` intent, pass `user_id`
- `app/routes/chat.py`: uses `current_user`, passes `user.id`

### 5. `app/main.py` — ReminderScheduler init

- Pass a `UserRepository` factory or connection so the scheduler can list users per tick.

### 6. Conftest + test fixtures

- `tests/conftest.py`: add fixtures:
  ```python
  @pytest.fixture
  def test_user(db_connection):
      from app.repositories.user_repository import UserRepository
      repo = UserRepository(db_connection)
      return repo.create("g-test", "test@example.com", "Test User", None)

  @pytest.fixture
  def authed_client(client, db_connection, test_user, monkeypatch):
      """A TestClient with a valid session cookie for test_user."""
      monkeypatch.setattr(
          "app.services.jwt_service.settings.session_secret",
          "test-secret-at-least-32-characters-long-for-hs256",
      )
      from app.services.jwt_service import issue_session_token
      client.cookies.set("ow_session", issue_session_token(test_user.id))
      return client
  ```

### 7. Update existing tests

Every test that calls a service method or hits a route needs `user_id`
threaded through. Pattern:

```python
# before
def test_create_commitment(service):
    commitment = service.create(CommitmentCreate(text="x"))

# after
def test_create_commitment(service, test_user):
    commitment = service.create(test_user.id, CommitmentCreate(text="x"))
```

For route tests, switch `client` fixture → `authed_client`.

**Affected test files (run pytest after each fix to surface the next):**
- `tests/unit/test_commitment_repository.py`
- `tests/unit/test_commitment_service.py`
- `tests/unit/test_commitment_parser_service.py`
- `tests/unit/test_briefing_service.py`
- `tests/unit/test_calendar_service.py`
- `tests/unit/test_google_calendar_provider.py`
- `tests/unit/test_stats_service.py`
- `tests/unit/test_chat_service.py`
- `tests/unit/test_push_service.py`
- `tests/unit/test_push_subscription_repository.py`
- `tests/unit/test_reminder_scheduler.py`
- `tests/integration/test_commitment_routes.py`
- `tests/integration/test_briefing_routes.py`
- `tests/integration/test_stats_routes.py`
- `tests/integration/test_calendar_routes.py`
- `tests/integration/test_push_routes.py`

### 8. Frontend (mostly unchanged)

The frontend doesn't need significant changes — auth context already
exists, all API calls already send the session cookie, and the backend
routes will route to the right user automatically. However:
- Consider adding a "Connect Google Calendar" button in `SettingsPanel.jsx`
  that links to `/calendar/connect/google` (kicks off the per-user OAuth flow)

---

## The pattern (cheat sheet)

For every remaining service/repo:

1. **Repository:** add `user_id: UUID` as first param of every method; add `WHERE user_id = ?` to every read; add `user_id` to every INSERT/UPDATE.
2. **Service:** add `user_id: UUID` as first param of every method; pass to repository.
3. **Route:** add `user: UserResponse = Depends(current_user)` to every endpoint; pass `user.id` to the service.

Imports needed in any updated file:
```python
from uuid import UUID  # in repos and services
from app.models.user import UserResponse  # in routes
from app.routes.auth import current_user  # in routes
```

---

## Verifying done-ness

After everything above is shipped:

```bash
cd backend
pytest -q                  # should be ~250+ tests, all green
```

Then manually:

```bash
# Start backend
python -m uvicorn app.main:app --reload --port 8000

# In another terminal
cd frontend && npm run dev

# Browser
# - Sign in with one Google account → create a commitment → see it
# - Sign out
# - Sign in with a DIFFERENT Google account → should see ZERO commitments
# - Create commitments here → confirm they don't appear in the first account
```

That's the success criterion for Slice 12.

---

## Suggested commit message for the checkpoint

```
feat(slice-12): start multi-tenancy refactor (WIP — see SLICE_12_PROGRESS.md)

Partial implementation of multi-tenancy per ADR-0010:
- Migrations 003 (user_id columns) + 004 (google_tokens)
- Commitments layer fully scoped by user_id (repo + service + parser + routes)
- Briefings layer fully scoped by user_id (repo + service + routes)
- ADR-0010 written

Remaining: calendar/push/stats/chat services + tests. See
docs/SLICE_12_PROGRESS.md for the pattern and checklist.

DO NOT MERGE — tests are intentionally broken in this commit.
```
