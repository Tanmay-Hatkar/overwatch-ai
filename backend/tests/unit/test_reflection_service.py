"""
test_reflection_service.py — Unit tests for ReflectionService.

Mirrors test_briefing_service.py's structure. The LLM is mocked at the
import site in reflection_service. Tests cover:
  - Bucketing logic (done / open / abandoned / recurring roll-forward heuristic)
  - Empty-day path
  - LLM unavailable / empty response
  - Whitespace handling
  - Caching (hit/miss, strict `>` freshness, force_regenerate)
"""

from datetime import UTC, datetime, time
from uuid import uuid4
from unittest.mock import patch

import pytest

from app.models.commitment import CommitmentCreate, CommitmentStatus, CommitmentUpdate, Recurrence
from app.models.reflection import ReflectionResponse
from app.repositories.reflection_repository import ReflectionRepository
from app.services.commitment_service import CommitmentService
from app.services.reflection_service import ReflectionGenerationError, ReflectionService

LLM_PATCH_TARGET = "app.services.reflection_service.call_llm"

UID = uuid4()


def _today_at_noon_utc() -> datetime:
    """A stable, deterministic 'today, mid-day' timestamp — see the
    roll-forward tests below for why this beats an offset from live now()."""
    return datetime.combine(datetime.now(UTC).date(), time(12, 0), tzinfo=UTC)


@pytest.fixture
def reflection_repo(db_connection) -> ReflectionRepository:
    """Fresh reflection repository wired to the in-memory db."""
    return ReflectionRepository(db_connection)


@pytest.fixture
def reflection_service(
    service: CommitmentService, reflection_repo: ReflectionRepository
) -> ReflectionService:
    """ReflectionService wired to the in-memory commitment service + reflection repo."""
    return ReflectionService(service, reflection_repo)


# ---------------------------------------------------------------------------
# Happy paths / empty day
# ---------------------------------------------------------------------------


def test_generates_reflection_with_no_commitments(
    reflection_service: ReflectionService,
) -> None:
    """Reflection works (and is non-empty) even with no commitments at all."""
    with patch(LLM_PATCH_TARGET, return_value="Nothing on the books today."):
        result = reflection_service.get_today(UID)

    assert isinstance(result, ReflectionResponse)
    assert result.content == "Nothing on the books today."
    assert result.done_count == 0
    assert result.open_count == 0
    assert result.abandoned_count == 0


def test_strips_whitespace_from_reflection_content(
    reflection_service: ReflectionService,
) -> None:
    """Leading/trailing whitespace is stripped before returning."""
    with patch(LLM_PATCH_TARGET, return_value="   Reflection here.   "):
        result = reflection_service.get_today(UID)
    assert result.content == "Reflection here."


# ---------------------------------------------------------------------------
# Bucketing logic
# ---------------------------------------------------------------------------


def test_buckets_done_today(
    reflection_service: ReflectionService, service: CommitmentService
) -> None:
    """A commitment marked done today lands in the done bucket, and its
    text reaches the LLM prompt."""
    c = service.create(UID, CommitmentCreate(text="Send report", due_at=None))
    service.update(UID, c.id, CommitmentUpdate(status=CommitmentStatus.DONE))

    with patch(LLM_PATCH_TARGET, return_value="ok") as mock:
        result = reflection_service.get_today(UID)

    assert result.done_count == 1
    assert result.open_count == 0
    user_prompt = mock.call_args.kwargs["user_prompt"]
    assert "Send report" in user_prompt


def test_buckets_still_open(
    reflection_service: ReflectionService, service: CommitmentService
) -> None:
    """A plain open commitment (not done, not recurring) lands in the open bucket."""
    service.create(UID, CommitmentCreate(text="Update docs", due_at=None))

    with patch(LLM_PATCH_TARGET, return_value="ok"):
        result = reflection_service.get_today(UID)

    assert result.open_count == 1
    assert result.done_count == 0


def test_buckets_abandoned_today(
    reflection_service: ReflectionService, service: CommitmentService
) -> None:
    """A commitment abandoned today lands in the abandoned bucket, not open or done."""
    c = service.create(UID, CommitmentCreate(text="Old plan", due_at=None))
    service.update(UID, c.id, CommitmentUpdate(status=CommitmentStatus.ABANDONED))

    with patch(LLM_PATCH_TARGET, return_value="ok"):
        result = reflection_service.get_today(UID)

    assert result.abandoned_count == 1
    assert result.done_count == 0
    assert result.open_count == 0


def test_recurring_rollforward_counts_as_done_today(
    reflection_service: ReflectionService, service: CommitmentService
) -> None:
    """A recurring commitment completed today rolls forward and stays OPEN
    with a future due_at (ADR-0015) — the reflection's heuristic counts it
    as done-today rather than showing it as an untouched open item."""
    # Anchored to "today at noon UTC", not an offset from live "now". A
    # relative offset (e.g. now-1h) only guarantees the rolled-forward
    # due_at (+1 day) is chronologically later than "now" — not that its
    # *calendar date* is later than "today". Near UTC midnight those are
    # different things: now-1h + 1 day can still land on today's date,
    # making the roll-forward heuristic (due_at.date() > today) miss it.
    # Noon UTC today + 1 day is unconditionally tomorrow, any time of day.
    due = _today_at_noon_utc()
    c = service.create(
        UID, CommitmentCreate(text="Night routine", due_at=due, recurrence=Recurrence.DAILY)
    )
    service.update(UID, c.id, CommitmentUpdate(status=CommitmentStatus.DONE))  # rolls forward

    with patch(LLM_PATCH_TARGET, return_value="ok"):
        result = reflection_service.get_today(UID)

    assert result.done_count == 1
    assert result.open_count == 0


def test_untouched_recurring_commitment_stays_open(
    reflection_service: ReflectionService, service: CommitmentService
) -> None:
    """A recurring commitment that was NOT touched today doesn't trigger the
    roll-forward heuristic — it's just an ordinary open item."""
    # Same anchor as above: noon UTC today is unconditionally NOT past
    # today's date, so the heuristic's due_at.date() > today check reliably
    # comes back False, regardless of what time of day the test runs.
    future = _today_at_noon_utc()
    service.create(
        UID, CommitmentCreate(text="Night routine", due_at=future, recurrence=Recurrence.DAILY)
    )

    with patch(LLM_PATCH_TARGET, return_value="ok"):
        result = reflection_service.get_today(UID)

    assert result.open_count == 1
    assert result.done_count == 0


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_raises_when_llm_returns_none(reflection_service: ReflectionService) -> None:
    """call_llm returning None (all providers failed) raises ReflectionGenerationError."""
    with patch(LLM_PATCH_TARGET, return_value=None):
        with pytest.raises(ReflectionGenerationError, match="empty"):
            reflection_service.get_today(UID)


def test_raises_when_llm_returns_whitespace_only(
    reflection_service: ReflectionService,
) -> None:
    """Whitespace-only LLM response is treated as empty."""
    with patch(LLM_PATCH_TARGET, return_value="   \n  "):
        with pytest.raises(ReflectionGenerationError, match="empty"):
            reflection_service.get_today(UID)


# ---------------------------------------------------------------------------
# Caching behavior
# ---------------------------------------------------------------------------


def test_first_call_marks_reflection_as_fresh(reflection_service: ReflectionService) -> None:
    """The first call to get_today() generates fresh (cached=False)."""
    with patch(LLM_PATCH_TARGET, return_value="Fresh reflection."):
        result = reflection_service.get_today(UID)
    assert result.cached is False


def test_second_call_returns_cached_reflection(reflection_service: ReflectionService) -> None:
    """A second call with no commitment changes returns the cache (cached=True)."""
    with patch(LLM_PATCH_TARGET, return_value="First reflection.") as mock:
        first = reflection_service.get_today(UID)
        second = reflection_service.get_today(UID)

    assert first.cached is False
    assert second.cached is True
    assert second.content == first.content
    assert mock.call_count == 1  # second call hit the cache


def test_cache_invalidated_when_commitment_changes(
    reflection_service: ReflectionService, service: CommitmentService
) -> None:
    """Modifying a commitment after caching invalidates the reflection
    (strict `>` comparison against latest_commitment_update, per ADR-0004)."""
    with patch(LLM_PATCH_TARGET, return_value="First reflection."):
        reflection_service.get_today(UID)

    service.create(UID, CommitmentCreate(text="New task", due_at=None))

    with patch(LLM_PATCH_TARGET, return_value="Regenerated reflection.") as mock:
        result = reflection_service.get_today(UID)

    assert result.cached is False
    assert result.content == "Regenerated reflection."
    assert mock.call_count == 1


def test_force_regenerate_skips_cache(reflection_service: ReflectionService) -> None:
    """force_regenerate=True bypasses the cache even when it would be fresh."""
    with patch(LLM_PATCH_TARGET, return_value="First.") as mock:
        reflection_service.get_today(UID)
        reflection_service.get_today(UID, force_regenerate=True)

    assert mock.call_count == 2  # both calls hit the LLM
