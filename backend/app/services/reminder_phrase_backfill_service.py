"""
reminder_phrase_backfill_service.py — One-time backfill of reminder_phrase
for existing open commitments (ADR-0021).

Commitments created before the reminder_phrase field existed have it as
None. This service generates it for those rows via a single, narrow LLM
call per commitment (text/due_at as fixed context — never re-derived), so
running the backfill script can never alter an existing due date or text.

Invoked by backend/scripts/backfill_reminder_phrases.py — not wired into
any scheduled job; run manually, once, after deploying this migration.
"""

import json
import logging
from datetime import datetime
from uuid import UUID

from app.agents.orchestrator import call_llm
from app.config import settings
from app.models.commitment import CommitmentStatus, CommitmentUpdate
from app.prompts.reminder_phrase_backfill import SYSTEM_PROMPT, USER_TEMPLATE
from app.services.commitment_service import CommitmentService

logger = logging.getLogger(__name__)


class ReminderPhraseBackfillService:
    """Generates and persists reminder_phrase for commitments missing it."""

    def __init__(self, commitment_service: CommitmentService) -> None:
        self._service = commitment_service

    def backfill_user(self, user_id: UUID) -> tuple[int, int]:
        """
        Backfill reminder_phrase for one user's open commitments.

        Args:
            user_id: The user whose open commitments to scan.

        Returns:
            (updated_count, skipped_count) — skipped covers commitments where
            the LLM call failed or returned an unusable phrase; those are
            left None and can be retried by running the script again
            (idempotent: only rows still missing reminder_phrase are touched).
        """
        commitments = self._service.list(user_id, status=CommitmentStatus.OPEN)
        missing = [c for c in commitments if not c.reminder_phrase]

        updated = 0
        skipped = 0
        for commitment in missing:
            phrase = self._generate_phrase(commitment.text, commitment.due_at)
            if phrase is None:
                skipped += 1
                continue
            self._service.update(
                user_id, commitment.id, CommitmentUpdate(reminder_phrase=phrase)
            )
            updated += 1

        return updated, skipped

    def _generate_phrase(self, text: str, due_at: datetime | None) -> str | None:
        """
        Call the LLM for a single commitment's reminder_phrase.

        Never raises — any failure (LLM unavailable, malformed JSON, missing
        field) logs a warning and returns None so the caller can skip and
        retry later rather than aborting the whole backfill run.
        """
        due_at_str = due_at.isoformat() if due_at is not None else "null"
        user_prompt = USER_TEMPLATE.format(text=text, due_at=due_at_str)

        raw = call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=settings.llm_intent_temperature,
        )
        if raw is None:
            logger.warning(f"Backfill: LLM unavailable for commitment text={text!r}")
            return None

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0]

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"Backfill: LLM returned non-JSON for text={text!r}: {raw!r}")
            return None

        phrase = parsed.get("reminder_phrase") if isinstance(parsed, dict) else None
        if not isinstance(phrase, str) or not phrase.strip():
            logger.warning(f"Backfill: LLM returned invalid reminder_phrase for text={text!r}")
            return None

        return phrase.strip()
