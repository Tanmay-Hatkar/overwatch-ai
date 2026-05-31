"""
test_briefing_service.py — Unit tests for BriefingService.

The LLM is mocked at the import site in briefing_service. Tests cover:
  - Bucketing logic (today / overdue / future / no-due / done)
  - Empty state
  - LLM unavailable / empty response
  - Whitespace handling
  - Prompt construction (commitment text appears in the user prompt)
"""

from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.briefing import BriefingResponse
from app.models.commitment import CommitmentCreate, CommitmentStatus, CommitmentUpdate
from app.services.briefing_service import BriefingGenerationError, BriefingService
from app.services.commitment_service import CommitmentService

LLM_PATCH_TARGET = "app.services.briefing_service.call_llm"


@pytest.fixture
def briefing_service(service: CommitmentService) -> BriefingService:
    """BriefingService wired to the in-memory CommitmentService fixture."""
    return BriefingService(service)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_generates_briefing_with_no_commitments(briefing_service: BriefingService) -> None:
    """Briefing works (and is non-empty) even with no commitments."""
    with patch(LLM_PATCH_TARGET, return_value="Good morning. Nothing today."):
        result = briefing_service.generate_today()

    assert isinstance(result, BriefingResponse)
    assert result.content == "Good morning. Nothing today."
    assert result.today_count == 0
    assert result.overdue_count == 0


def test_strips_whitespace_from_briefing_content(briefing_service: BriefingService) -> None:
    """Leading/trailing whitespace is stripped before returning."""
    with patch(LLM_PATCH_TARGET, return_value="   Briefing here.   "):
        result = briefing_service.generate_today()
    assert result.content == "Briefing here."


# ---------------------------------------------------------------------------
# Bucketing logic
# ---------------------------------------------------------------------------


def _today_at(hour: int) -> datetime:
    """Helper: a datetime today at the given hour."""
    return datetime.combine(date.today(), datetime.min.time().replace(hour=hour))


def test_buckets_today_commitments(
    briefing_service: BriefingService, service: CommitmentService
) -> None:
    """Open commitments with due_at on today's date go in the today bucket."""
    service.create(CommitmentCreate(text="Call mom", due_at=_today_at(15)))

    with patch(LLM_PATCH_TARGET, return_value="briefing") as mock:
        result = briefing_service.generate_today()

    assert result.today_count == 1
    assert result.overdue_count == 0
    # Verify the commitment text reached the LLM prompt
    user_prompt = mock.call_args.kwargs["user_prompt"]
    assert "Call mom" in user_prompt


def test_buckets_overdue_commitments(
    briefing_service: BriefingService, service: CommitmentService
) -> None:
    """Commitments with due_at before today are overdue."""
    yesterday = datetime.now() - timedelta(days=1)
    service.create(CommitmentCreate(text="Old task", due_at=yesterday))

    with patch(LLM_PATCH_TARGET, return_value="briefing"):
        result = briefing_service.generate_today()

    assert result.today_count == 0
    assert result.overdue_count == 1


def test_excludes_commitments_without_due_at(
    briefing_service: BriefingService, service: CommitmentService
) -> None:
    """Floating commitments (no due_at) don't appear in either bucket."""
    service.create(CommitmentCreate(text="Sometime task", due_at=None))

    with patch(LLM_PATCH_TARGET, return_value="briefing"):
        result = briefing_service.generate_today()

    assert result.today_count == 0
    assert result.overdue_count == 0


def test_excludes_done_commitments(
    briefing_service: BriefingService, service: CommitmentService
) -> None:
    """Done commitments don't appear in the briefing."""
    c = service.create(CommitmentCreate(text="Done thing", due_at=_today_at(12)))
    service.update(c.id, CommitmentUpdate(status=CommitmentStatus.DONE))

    with patch(LLM_PATCH_TARGET, return_value="briefing"):
        result = briefing_service.generate_today()

    assert result.today_count == 0


def test_excludes_future_commitments(
    briefing_service: BriefingService, service: CommitmentService
) -> None:
    """Commitments due tomorrow or later don't appear in today's briefing."""
    tomorrow = datetime.now() + timedelta(days=1)
    service.create(CommitmentCreate(text="Tomorrow task", due_at=tomorrow))

    with patch(LLM_PATCH_TARGET, return_value="briefing"):
        result = briefing_service.generate_today()

    assert result.today_count == 0
    assert result.overdue_count == 0


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_raises_when_llm_returns_none(briefing_service: BriefingService) -> None:
    """call_llm returning None (all providers failed) raises BriefingGenerationError."""
    with patch(LLM_PATCH_TARGET, return_value=None):
        with pytest.raises(BriefingGenerationError, match="empty"):
            briefing_service.generate_today()


def test_raises_when_llm_returns_whitespace_only(briefing_service: BriefingService) -> None:
    """Whitespace-only LLM response is treated as empty."""
    with patch(LLM_PATCH_TARGET, return_value="   \n  "):
        with pytest.raises(BriefingGenerationError, match="empty"):
            briefing_service.generate_today()
