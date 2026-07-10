"""
reflection_service.py — Generate (and cache) natural-language evening
reflections.

Pipeline for `get_today()` mirrors briefing_service.py's `get_today()`
exactly (see docs/adr/0004-briefing-caching-strategy.md, reused here per
docs/adr/0018-evening-reflection.md):
  1. Look up the cached reflection for today (if any).
  2. If cached AND no commitment has been updated since it was generated
     (strict `>` comparison — see ADR-0004), return it. No LLM call.
  3. Otherwise: fetch commitments, bucket by outcome, call the LLM,
     persist the result, return it.

Buckets are computed in Python from CommitmentService.list() — no new
repository queries needed:
  - done_today: status=done, touched today.
  - still_open: status=open (today + overdue both count — the reflection
    doesn't need the morning briefing's today/overdue split, just "what's
    still hanging").
  - abandoned_today: status=abandoned, touched today.

Recurring roll-forward heuristic: completing a recurring commitment rolls
it forward to its next occurrence and reopens it instead of closing it
(ADR-0015) — so it never actually reaches status=done in storage. We
approximate "completed today" for these by also counting any row where
recurrence != none AND it was touched today AND its due_at now points past
today (i.e. it already rolled forward) as done-today. This is a heuristic,
not a ledger of individual completions — the same known gap ADR-0015
already accepts (no audit trail of each individual recurring completion,
only the latest roll-forward state).
"""

import logging
from datetime import UTC, date, datetime
from uuid import UUID

from app.agents.orchestrator import call_llm
from app.models.commitment import CommitmentResponse, CommitmentStatus, Recurrence
from app.models.reflection import ReflectionResponse
from app.prompts.evening_reflection import SYSTEM_PROMPT, USER_TEMPLATE
from app.repositories.reflection_repository import ReflectionRepository
from app.services.commitment_service import CommitmentService

logger = logging.getLogger(__name__)


class ReflectionGenerationError(Exception):
    """Raised when the LLM is unavailable or returns an empty response."""


class ReflectionService:
    """
    Generates and caches evening reflections.

    Composed of:
      - CommitmentService (to fetch commitments + check freshness)
      - ReflectionRepository (to read/write the cache)
    """

    def __init__(
        self,
        commitment_service: CommitmentService,
        repository: ReflectionRepository,
    ) -> None:
        self._service = commitment_service
        self._repo = repository

    def get_today(self, user_id: UUID, force_regenerate: bool = False) -> ReflectionResponse:
        """
        Get this user's reflection for today — cached if fresh, else regenerated.

        Args:
            user_id: Owner of the reflection.
            force_regenerate: If True, skip the cache and always regenerate.

        Returns:
            ReflectionResponse with `cached=True` for cache hits,
            `cached=False` for fresh generations.

        Raises:
            ReflectionGenerationError: If the LLM is unavailable when we
                need it.
        """
        # UTC, not local server date: unlike the morning briefing (which only
        # ever compares against due_at, whatever timezone the caller passed
        # in), the reflection buckets by `updated_at`, which the repository
        # always stamps in UTC. Using the local server date here would drift
        # bucketing whenever the server's system timezone isn't UTC.
        today = datetime.now(UTC).date()

        if not force_regenerate:
            cached = self._repo.get_for_date(user_id, today)
            if cached is not None and self._is_cache_fresh(user_id, cached):
                logger.info("Returning cached reflection for user %s on %s", user_id, today)
                return cached

        return self._generate_and_save(user_id, today)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_cache_fresh(self, user_id: UUID, cached: ReflectionResponse) -> bool:
        """
        Fresh if generated STRICTLY after the user's most recent commitment
        update (ADR-0004's exact rule). If the user has no commitments, the
        cache is trivially fresh.
        """
        latest = self._service.latest_commitment_update(user_id)
        if latest is None:
            return True
        return cached.generated_at > latest

    def _generate_and_save(self, user_id: UUID, today: date) -> ReflectionResponse:
        """Generate a fresh reflection and persist it (upsert) for this user+date."""
        done_today, still_open, abandoned_today = self._bucket_commitments(user_id, today)

        user_prompt = USER_TEMPLATE.format(
            today_name=today.strftime("%A"),
            today_date=today.isoformat(),
            done_count=len(done_today),
            done_list=self._format_list(done_today),
            open_count=len(still_open),
            open_list=self._format_list(still_open),
            abandoned_count=len(abandoned_today),
            abandoned_list=self._format_list(abandoned_today),
        )

        raw = call_llm(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)

        if not raw or not raw.strip():
            raise ReflectionGenerationError("LLM returned empty reflection")

        fresh = ReflectionResponse(
            content=raw.strip(),
            done_count=len(done_today),
            open_count=len(still_open),
            abandoned_count=len(abandoned_today),
            generated_at=datetime.now(UTC),
            cached=False,  # this generation is fresh
        )

        # Persist to cache (upsert). The persisted version comes back marked
        # cached=True, but we return the fresh-flagged version to the caller
        # so the client sees this was a fresh generation.
        self._repo.save(user_id, fresh, today)

        logger.info(
            "Generated reflection for user %s on %s: %d done, %d open, %d abandoned, %d chars",
            user_id, today, len(done_today), len(still_open), len(abandoned_today), len(raw),
        )

        return fresh

    def _bucket_commitments(
        self, user_id: UUID, today: date
    ) -> tuple[list[CommitmentResponse], list[CommitmentResponse], list[CommitmentResponse]]:
        """
        Partition the user's commitments into done-today, still-open, and
        abandoned-today buckets for the reflection. See module docstring for
        the recurring roll-forward heuristic.
        """
        all_commitments = self._service.list(user_id)

        done_today: list[CommitmentResponse] = []
        still_open: list[CommitmentResponse] = []
        abandoned_today: list[CommitmentResponse] = []

        for c in all_commitments:
            touched_today = c.updated_at.date() == today
            if c.status == CommitmentStatus.DONE and touched_today:
                done_today.append(c)
            elif c.status == CommitmentStatus.ABANDONED and touched_today:
                abandoned_today.append(c)
            elif c.status == CommitmentStatus.OPEN:
                if self._is_recurring_rollforward_today(c, today, touched_today):
                    done_today.append(c)
                else:
                    still_open.append(c)

        return done_today, still_open, abandoned_today

    @staticmethod
    def _is_recurring_rollforward_today(
        c: CommitmentResponse, today: date, touched_today: bool
    ) -> bool:
        """
        Heuristic: a recurring commitment touched today whose due_at now
        points past today has already rolled forward (ADR-0015) — treat it
        as completed today rather than as an untouched open item.
        """
        return (
            c.recurrence != Recurrence.NONE
            and touched_today
            and c.due_at is not None
            and c.due_at.date() > today
        )

    @staticmethod
    def _format_list(commitments: list[CommitmentResponse]) -> str:
        """Format a list of commitments as a multi-line string for the prompt."""
        if not commitments:
            return "(none)"
        return "\n".join(f"- {c.text}" for c in commitments)
