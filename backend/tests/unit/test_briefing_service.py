"""
test_briefing_service.py — Unit tests for BriefingService.

The LLM is mocked at the import site in briefing_service. Tests cover:
  - Bucketing logic (today / overdue / future / no-due / done)
  - Empty state
  - LLM unavailable / empty response
  - Whitespace handling
  - Prompt construction (commitment text appears in the user prompt)
"""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from unittest.mock import patch

import pytest

from app.models.briefing import BriefingResponse
from app.models.commitment import CommitmentCreate, CommitmentStatus, CommitmentUpdate
from app.providers.mock_calendar_provider import MockCalendarProvider
from app.repositories.briefing_repository import BriefingRepository
from app.services.briefing_service import BriefingGenerationError, BriefingService
from app.services.calendar_service import CalendarService
from app.services.commitment_service import CommitmentService

LLM_PATCH_TARGET = "app.services.briefing_service.call_llm"

UID = uuid4()


@pytest.fixture
def briefing_repo(db_connection) -> BriefingRepository:
    """Fresh briefing repository wired to the in-memory db."""
    return BriefingRepository(db_connection)


@pytest.fixture
def briefing_service(
    service: CommitmentService, briefing_repo: BriefingRepository
) -> BriefingService:
    """BriefingService wired to the in-memory commitment service + briefing repo."""
    return BriefingService(service, briefing_repo)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_generates_briefing_with_no_commitments(briefing_service: BriefingService) -> None:
    """Briefing works (and is non-empty) even with no commitments."""
    with patch(LLM_PATCH_TARGET, return_value="Good morning. Nothing today."):
        result = briefing_service.generate_today(UID)

    assert isinstance(result, BriefingResponse)
    assert result.content == "Good morning. Nothing today."
    assert result.today_count == 0
    assert result.overdue_count == 0
    assert result.floating_count == 0


def test_strips_whitespace_from_briefing_content(briefing_service: BriefingService) -> None:
    """Leading/trailing whitespace is stripped before returning."""
    with patch(LLM_PATCH_TARGET, return_value="   Briefing here.   "):
        result = briefing_service.generate_today(UID)
    assert result.content == "Briefing here."


# ---------------------------------------------------------------------------
# Bucketing logic
# ---------------------------------------------------------------------------


def _today_at(hour: int) -> datetime:
    """Helper: a UTC-aware datetime today (UTC calendar date) at the given
    hour. UTC-anchored, not server-local — BriefingService buckets 'today'
    against the caller's timezone (UTC when none is passed, as here), so a
    naive/local-date fixture would silently disagree with it on any
    non-UTC machine (see ADR-0023's timezone-bucketing follow-up)."""
    return datetime.combine(datetime.now(UTC).date(), datetime.min.time().replace(hour=hour), tzinfo=UTC)


def test_buckets_today_commitments(
    briefing_service: BriefingService, service: CommitmentService
) -> None:
    """Open commitments with due_at on today's date go in the today bucket."""
    service.create(UID, CommitmentCreate(text="Call mom", due_at=_today_at(15)))

    with patch(LLM_PATCH_TARGET, return_value="briefing") as mock:
        result = briefing_service.generate_today(UID)

    assert result.today_count == 1
    assert result.overdue_count == 0
    # Verify the commitment text reached the LLM prompt
    user_prompt = mock.call_args.kwargs["user_prompt"]
    assert "Call mom" in user_prompt


def test_buckets_overdue_commitments(
    briefing_service: BriefingService, service: CommitmentService
) -> None:
    """Commitments with due_at before today are overdue."""
    yesterday = datetime.now(UTC) - timedelta(days=1)
    service.create(UID, CommitmentCreate(text="Old task", due_at=yesterday))

    with patch(LLM_PATCH_TARGET, return_value="briefing"):
        result = briefing_service.generate_today(UID)

    assert result.today_count == 0
    assert result.overdue_count == 1


def test_floating_commitments_counted_separately(
    briefing_service: BriefingService, service: CommitmentService
) -> None:
    """Floating commitments (no due_at) don't count as today/overdue, but
    are surfaced via their own floating_count (ADR-0023) — they used to be
    silently excluded from the briefing entirely."""
    service.create(UID, CommitmentCreate(text="Sometime task", due_at=None))

    with patch(LLM_PATCH_TARGET, return_value="briefing") as mock:
        result = briefing_service.generate_today(UID)

    assert result.today_count == 0
    assert result.overdue_count == 0
    assert result.floating_count == 1
    user_prompt = mock.call_args.kwargs["user_prompt"]
    assert "Sometime task" in user_prompt


def test_excludes_done_commitments(
    briefing_service: BriefingService, service: CommitmentService
) -> None:
    """Done commitments don't appear in the briefing."""
    c = service.create(UID, CommitmentCreate(text="Done thing", due_at=_today_at(12)))
    service.update(UID, c.id, CommitmentUpdate(status=CommitmentStatus.DONE))

    with patch(LLM_PATCH_TARGET, return_value="briefing"):
        result = briefing_service.generate_today(UID)

    assert result.today_count == 0


def test_excludes_future_commitments(
    briefing_service: BriefingService, service: CommitmentService
) -> None:
    """Commitments due tomorrow or later don't appear in today's briefing."""
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    service.create(UID, CommitmentCreate(text="Tomorrow task", due_at=tomorrow))

    with patch(LLM_PATCH_TARGET, return_value="briefing"):
        result = briefing_service.generate_today(UID)

    assert result.today_count == 0
    assert result.overdue_count == 0


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_raises_when_llm_returns_none(briefing_service: BriefingService) -> None:
    """call_llm returning None (all providers failed) raises BriefingGenerationError."""
    with patch(LLM_PATCH_TARGET, return_value=None):
        with pytest.raises(BriefingGenerationError, match="empty"):
            briefing_service.generate_today(UID)


def test_raises_when_llm_returns_whitespace_only(briefing_service: BriefingService) -> None:
    """Whitespace-only LLM response is treated as empty."""
    with patch(LLM_PATCH_TARGET, return_value="   \n  "):
        with pytest.raises(BriefingGenerationError, match="empty"):
            briefing_service.generate_today(UID)


# ---------------------------------------------------------------------------
# Caching behavior
# ---------------------------------------------------------------------------


def test_first_call_marks_briefing_as_fresh(briefing_service: BriefingService) -> None:
    """The first call to get_today() generates fresh (cached=False)."""
    with patch(LLM_PATCH_TARGET, return_value="Fresh briefing."):
        result = briefing_service.get_today(UID)
    assert result.cached is False


def test_second_call_returns_cached_briefing(briefing_service: BriefingService) -> None:
    """A second call with no commitment changes returns the cache (cached=True)."""
    with patch(LLM_PATCH_TARGET, return_value="First briefing.") as mock:
        first = briefing_service.get_today(UID)
        second = briefing_service.get_today(UID)

    assert first.cached is False
    assert second.cached is True
    assert second.content == first.content
    # LLM should only have been called once — second call hit the cache
    assert mock.call_count == 1


def test_cache_invalidated_when_commitment_changes(
    briefing_service: BriefingService, service: CommitmentService
) -> None:
    """Modifying a commitment after caching invalidates the briefing."""
    with patch(LLM_PATCH_TARGET, return_value="First briefing."):
        briefing_service.get_today(UID)

    # Create a commitment (this updates the commitments table)
    service.create(UID, CommitmentCreate(text="New task", due_at=None))

    with patch(LLM_PATCH_TARGET, return_value="Regenerated briefing.") as mock:
        result = briefing_service.get_today(UID)

    assert result.cached is False
    assert result.content == "Regenerated briefing."
    assert mock.call_count == 1


def test_force_regenerate_skips_cache(briefing_service: BriefingService) -> None:
    """force_regenerate=True bypasses the cache even when it would be fresh."""
    with patch(LLM_PATCH_TARGET, return_value="First.") as mock:
        briefing_service.get_today(UID)
        briefing_service.get_today(UID, force_regenerate=True)

    assert mock.call_count == 2  # both calls hit the LLM


# ---------------------------------------------------------------------------
# Calendar event injection
# ---------------------------------------------------------------------------


def test_briefing_without_calendar_service_renders_no_events(
    briefing_service: BriefingService,
) -> None:
    """A briefing service without a calendar service injects '(none)' for events."""
    with patch(LLM_PATCH_TARGET, return_value="OK briefing.") as mock:
        briefing_service.generate_today(UID)

    user_prompt = mock.call_args.kwargs["user_prompt"]
    # When no calendar service is wired, the events count should be 0
    assert "Calendar events for today (0):" in user_prompt
    assert "(none)" in user_prompt


def test_briefing_with_calendar_service_injects_events(
    service: CommitmentService, briefing_repo: BriefingRepository
) -> None:
    """When a calendar service is wired, events appear in the prompt."""
    calendar_service = CalendarService(MockCalendarProvider())
    service_with_cal = BriefingService(service, briefing_repo, calendar_service)

    with patch(LLM_PATCH_TARGET, return_value="OK briefing.") as mock:
        service_with_cal.generate_today(UID)

    user_prompt = mock.call_args.kwargs["user_prompt"]
    # Mock provider returns events on weekdays, none on weekends —
    # we just verify the prompt has the events section formatted correctly
    assert "Calendar events for today" in user_prompt
    # On weekdays, the mock provider returns 3 named events
    if date.today().weekday() < 5:
        assert "Daily standup" in user_prompt
        assert "Lunch with Alex" in user_prompt
        assert "1:1 with manager" in user_prompt
