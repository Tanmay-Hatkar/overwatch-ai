"""
briefing_service.py — Generate (and cache) natural-language morning briefings.

Pipeline for `get_today()`:
  1. Look up the cached briefing for today (if any).
  2. If cached AND no commitment has been updated since it was generated,
     return it. (Fast path: no LLM call.)
  3. Otherwise: fetch commitments, bucket by due-date, call the LLM,
     persist the result, return it.

Cache invalidation strategy: timestamp-based. We compare the briefing's
`generated_at` to the most recent `updated_at` of any commitment. If the
commitment table has changed since the briefing was generated, the
briefing is considered stale and we regenerate.

Limitation: this doesn't catch *deletions* (we have no tombstone). If a
commitment is deleted, the briefing may still mention it until the next
commitment mutation triggers regeneration, or the user hits "refresh"
(force_regenerate=True).
"""

import logging
from datetime import UTC, date, datetime

from app.agents.orchestrator import call_llm
from app.models.briefing import BriefingResponse
from app.models.commitment import CommitmentResponse, CommitmentStatus
from app.models.event import CalendarEvent
from app.prompts.morning_briefing import SYSTEM_PROMPT, USER_TEMPLATE
from app.repositories.briefing_repository import BriefingRepository
from app.services.calendar_service import CalendarService
from app.services.commitment_service import CommitmentService

logger = logging.getLogger(__name__)


class BriefingGenerationError(Exception):
    """Raised when the LLM is unavailable or returns an empty response."""


class BriefingService:
    """
    Generates and caches morning briefings.

    Composed of:
      - CommitmentService (to fetch commitments + check freshness)
      - BriefingRepository (to read/write the cache)
    """

    def __init__(
        self,
        commitment_service: CommitmentService,
        repository: BriefingRepository,
        calendar_service: CalendarService | None = None,
    ) -> None:
        self._service = commitment_service
        self._repo = repository
        # calendar_service is optional — older callers (and tests that don't
        # care about events) can omit it. When omitted, briefings render
        # with "(none)" in the events section.
        self._calendar = calendar_service

    def get_today(self, force_regenerate: bool = False) -> BriefingResponse:
        """
        Get today's briefing — cached if fresh, regenerated otherwise.

        Args:
            force_regenerate: If True, skip the cache and always regenerate.
                Used when the user explicitly hits "refresh."

        Returns:
            BriefingResponse with `cached=True` for cache hits,
            `cached=False` for fresh generations.

        Raises:
            BriefingGenerationError: If the LLM is unavailable when we need it.
        """
        today = date.today()

        if not force_regenerate:
            cached = self._repo.get_for_date(today)
            if cached is not None and self._is_cache_fresh(cached):
                logger.info(f"Returning cached briefing for {today}")
                return cached

        return self._generate_and_save(today)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_cache_fresh(self, cached: BriefingResponse) -> bool:
        """
        A cached briefing is fresh if it was generated STRICTLY after the
        most recent commitment update. Equal timestamps are treated as
        stale because we can't tell which event happened first at that
        precision — safer to regenerate.

        If there are no commitments at all, the cache is trivially fresh.
        """
        latest = self._service.latest_commitment_update()
        if latest is None:
            return True
        return cached.generated_at > latest

    def _generate_and_save(self, today: date) -> BriefingResponse:
        """Generate a fresh briefing and persist it (upsert) for the date."""
        today_commitments, overdue_commitments = self._bucket_commitments(today)
        events = self._fetch_events(today)

        user_prompt = USER_TEMPLATE.format(
            today_name=today.strftime("%A"),
            today_date=today.isoformat(),
            today_count=len(today_commitments),
            today_commitments=self._format_list(today_commitments),
            overdue_count=len(overdue_commitments),
            overdue_commitments=self._format_list(overdue_commitments),
            events_count=len(events),
            events=self._format_events(events),
        )

        raw = call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        if not raw or not raw.strip():
            raise BriefingGenerationError("LLM returned empty briefing")

        fresh = BriefingResponse(
            content=raw.strip(),
            today_count=len(today_commitments),
            overdue_count=len(overdue_commitments),
            # Use UTC to match CommitmentRepository's storage convention.
            # Comparing naive vs aware datetimes raises TypeError.
            generated_at=datetime.now(UTC),
            cached=False,  # this generation is fresh
        )

        # Persist to cache (upsert). The persisted version comes back marked
        # cached=True, but we return the fresh-flagged version to the caller
        # so the client sees this was a fresh generation.
        self._repo.save(fresh, today)

        logger.info(
            f"Generated briefing for {today}: {len(today_commitments)} today, "
            f"{len(overdue_commitments)} overdue, {len(raw)} chars"
        )

        return fresh

    def _bucket_commitments(
        self, today: date
    ) -> tuple[list[CommitmentResponse], list[CommitmentResponse]]:
        """
        Split open commitments into 'today' and 'overdue' buckets.

        Today:    open commitments with due_at on today's date.
        Overdue:  open commitments with due_at before today.
        Excluded: commitments without due_at (floating), future due dates,
                  and done/abandoned items.
        """
        all_open = self._service.list(status=CommitmentStatus.OPEN)

        today_bucket: list[CommitmentResponse] = []
        overdue_bucket: list[CommitmentResponse] = []

        for c in all_open:
            if c.due_at is None:
                continue
            due_date = c.due_at.date()
            if due_date == today:
                today_bucket.append(c)
            elif due_date < today:
                overdue_bucket.append(c)

        return today_bucket, overdue_bucket

    @staticmethod
    def _format_list(commitments: list[CommitmentResponse]) -> str:
        """Format a list of commitments as a multi-line string for the prompt."""
        if not commitments:
            return "(none)"
        lines = []
        for c in commitments:
            if c.due_at is not None:
                time_str = c.due_at.strftime("%I:%M %p").lstrip("0")
                lines.append(f"- {c.text} (due {time_str})")
            else:
                lines.append(f"- {c.text}")
        return "\n".join(lines)

    def _fetch_events(self, today: date) -> list[CalendarEvent]:
        """Get today's calendar events, or an empty list if none available."""
        if self._calendar is None:
            return []
        return self._calendar.list_today(today)

    @staticmethod
    def _format_events(events: list[CalendarEvent]) -> str:
        """Format calendar events as a multi-line string for the prompt."""
        if not events:
            return "(none)"
        lines = []
        for e in events:
            time_str = e.start_at.strftime("%I:%M %p").lstrip("0")
            lines.append(f"- {time_str} {e.title}")
        return "\n".join(lines)

    # Backwards-compat alias for the old API name. Existing callers/tests
    # using generate_today() now go through the cache path. To force
    # regeneration, use get_today(force_regenerate=True).
    generate_today = get_today
