"""
briefing_service.py — Generate natural-language morning briefings.

Pipeline:
  1. Fetch all open commitments via the injected CommitmentService.
  2. Bucket them by due-date relative to today (today / overdue / future).
  3. Format each bucket as a bulleted text list.
  4. Inject into the LLM prompt and call call_llm() at the default temperature.
  5. Wrap the result in a BriefingResponse with counts + timestamp.

Stateless — every call regenerates. Slice 4 has no caching. Future slices
can add a `briefings` table + per-day caching with a regenerate endpoint.
"""

import logging
from datetime import date, datetime

from app.agents.orchestrator import call_llm
from app.models.briefing import BriefingResponse
from app.models.commitment import CommitmentResponse, CommitmentStatus
from app.prompts.morning_briefing import SYSTEM_PROMPT, USER_TEMPLATE
from app.services.commitment_service import CommitmentService

logger = logging.getLogger(__name__)


class BriefingGenerationError(Exception):
    """Raised when the LLM is unavailable or returns an empty response."""


class BriefingService:
    """
    Generates morning briefings on demand.

    Composed of a CommitmentService — we fetch the user's open commitments,
    bucket them by due-date state, and inject the formatted lists into an
    LLM prompt.
    """

    def __init__(self, commitment_service: CommitmentService) -> None:
        self._service = commitment_service

    def generate_today(self) -> BriefingResponse:
        """
        Generate a fresh briefing for today.

        Returns:
            BriefingResponse with the LLM-generated content and counts.

        Raises:
            BriefingGenerationError: If the LLM is unavailable or returns
                an empty briefing.
        """
        today = date.today()
        today_commitments, overdue_commitments = self._bucket_commitments(today)

        user_prompt = USER_TEMPLATE.format(
            today_name=today.strftime("%A"),
            today_date=today.isoformat(),
            today_count=len(today_commitments),
            today_commitments=self._format_list(today_commitments),
            overdue_count=len(overdue_commitments),
            overdue_commitments=self._format_list(overdue_commitments),
        )

        raw = call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            # Default temperature (0.7) — warmer, varied phrasing.
        )

        if not raw or not raw.strip():
            raise BriefingGenerationError("LLM returned empty briefing")

        logger.info(
            f"Generated briefing: {len(today_commitments)} today, "
            f"{len(overdue_commitments)} overdue, {len(raw)} chars"
        )

        return BriefingResponse(
            content=raw.strip(),
            today_count=len(today_commitments),
            overdue_count=len(overdue_commitments),
            generated_at=datetime.now(),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
            # Future commitments are not in today's briefing.

        return today_bucket, overdue_bucket

    @staticmethod
    def _format_list(commitments: list[CommitmentResponse]) -> str:
        """
        Format a list of commitments as a multi-line string for the prompt.

        Returns '(none)' for empty lists so the LLM sees an explicit absence
        rather than a confusing blank section.
        """
        if not commitments:
            return "(none)"
        lines = []
        for c in commitments:
            if c.due_at is not None:
                # Portable across platforms: format with leading zero, then strip.
                time_str = c.due_at.strftime("%I:%M %p").lstrip("0")
                lines.append(f"- {c.text} (due {time_str})")
            else:
                lines.append(f"- {c.text}")
        return "\n".join(lines)
