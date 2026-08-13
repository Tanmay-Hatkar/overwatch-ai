"""
commitment_parser_service.py — Parse natural language into a commitment.

Pipeline:
  1. Build context (today's date, day name, 14-day date lookup table).
  2. Call the LLM with temperature=0 for deterministic JSON output.
  3. Strip markdown fences if present, parse JSON.
  4. Validate the shape (text required, due_at optional).
  5. Hand off to CommitmentService to persist.

If the LLM is unavailable or returns unparseable output, raises
CommitmentParseError. Routes catch this and return 503.
"""

import json
import logging
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.agents.orchestrator import call_llm
from app.config import settings
from app.models.commitment import CommitmentCreate, CommitmentResponse
from app.prompts.commitment_parser import SYSTEM_PROMPT, USER_TEMPLATE
from app.services.commitment_service import CommitmentService
from app.services.timezone_utils import resolve_timezone

logger = logging.getLogger(__name__)


class CommitmentParseError(Exception):
    """Raised when the LLM call fails or returns unparseable output."""


class CommitmentParserService:
    """
    Parses natural language messages into commitments via LLM.

    Composes a CommitmentService — when parsing succeeds, the resulting
    commitment is created through the standard service (no special path).
    """

    def __init__(self, commitment_service: CommitmentService) -> None:
        self._service = commitment_service

    def parse_and_create(
        self, user_id: UUID, message: str, timezone: str | None = None
    ) -> CommitmentResponse:
        """
        Parse a natural language message and create the commitment for user_id.

        Args:
            user_id: Owner of the new commitment.
            message: User's free-form input (e.g., "call mom tomorrow at 3pm").
            timezone: IANA timezone name used to resolve "today"/"now" for
                relative-date parsing. None falls back to UTC. Without this,
                a user meaningfully offset from UTC gets the wrong "today"
                for messages sent in the gap between the two dates.

        Returns:
            The newly created CommitmentResponse.

        Raises:
            CommitmentParseError: If the LLM is unavailable or returns
                output that can't be parsed into a valid commitment.
        """
        user_tz = resolve_timezone(timezone)
        user_prompt = self._build_user_prompt(message, user_tz)

        raw = call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=settings.llm_intent_temperature,
        )

        if raw is None:
            raise CommitmentParseError("LLM unavailable — no provider succeeded")

        parsed = self._parse_json(raw)
        text = self._extract_text(parsed)
        due_at = self._extract_due_at(parsed)
        reminder_phrase = self._extract_reminder_phrase(parsed)
        reminder_lead_minutes = self._extract_reminder_lead_minutes(parsed, due_at)

        payload = CommitmentCreate(
            text=text,
            due_at=due_at,
            reminder_phrase=reminder_phrase,
            reminder_lead_minutes=reminder_lead_minutes,
        )
        logger.info(f"Parsed commitment: text={text!r}, due_at={due_at}")
        return self._service.create(user_id, payload)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_user_prompt(self, message: str, user_tz: ZoneInfo) -> str:
        """Inject the user's local now + a 14-day lookup table into the user prompt."""
        today = datetime.now(user_tz)
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday",
                     "Friday", "Saturday", "Sunday"]
        today_name = day_names[today.weekday()]

        # Current local clock time, e.g. "4:42 PM" — lets the LLM resolve
        # "in 30 minutes", "tonight at 7", "in an hour" correctly.
        now_time = today.strftime("%I:%M %p").lstrip("0")

        # 14 days starting from today gives the LLM enough range to
        # handle "Friday", "next Tuesday", "in 10 days", etc.
        lookup_lines = []
        for i in range(14):
            day = today + timedelta(days=i)
            label = day_names[day.weekday()]
            marker = " (today)" if i == 0 else " (tomorrow)" if i == 1 else ""
            lookup_lines.append(f"  {day.date().isoformat()} — {label}{marker}")
        date_table = "\n".join(lookup_lines)

        return USER_TEMPLATE.format(
            message=message,
            now_time=now_time,
            today_name=today_name,
            today_date=today.date().isoformat(),
            date_table=date_table,
        )

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """Strip markdown fences if present, then parse JSON."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Some models wrap JSON in ```json ... ``` despite instructions.
            # Strip the opening fence (and language tag) and closing fence.
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0]

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"LLM returned non-JSON: {raw!r}")
            raise CommitmentParseError(f"LLM output was not valid JSON: {e}") from e

    @staticmethod
    def _extract_text(parsed: dict) -> str:
        """Pull and validate the 'text' field from the parsed JSON."""
        if not isinstance(parsed, dict) or "text" not in parsed:
            raise CommitmentParseError(f"LLM output missing 'text' field: {parsed!r}")
        text = parsed["text"]
        if not isinstance(text, str) or not text.strip():
            raise CommitmentParseError(f"LLM output has empty/invalid 'text': {parsed!r}")
        return text.strip()

    @staticmethod
    def _extract_due_at(parsed: dict) -> datetime | None:
        """
        Pull the 'due_at' field. Lenient: if invalid, log + return None
        rather than failing the whole parse. Better UX to create a
        commitment without a date than to fail entirely.
        """
        due_at_str = parsed.get("due_at")
        if due_at_str is None or due_at_str == "":
            return None
        try:
            return datetime.fromisoformat(due_at_str)
        except (ValueError, TypeError):
            logger.warning(f"LLM returned invalid due_at, dropping: {due_at_str!r}")
            return None

    @staticmethod
    def _extract_reminder_phrase(parsed: dict) -> str | None:
        """
        Pull the 'reminder_phrase' field. Lenient: this is a nice-to-have
        presentation string, not correctness-critical like text/due_at, so
        any missing/invalid value logs a warning and returns None rather
        than failing the whole parse — callers fall back to a templated
        string when this is None (see ADR-0021).
        """
        phrase = parsed.get("reminder_phrase")
        if phrase is None:
            return None
        if not isinstance(phrase, str) or not phrase.strip():
            logger.warning(f"LLM returned invalid reminder_phrase, dropping: {phrase!r}")
            return None
        return phrase.strip()

    @staticmethod
    def _extract_reminder_lead_minutes(parsed: dict, due_at: datetime | None) -> int:
        """
        Pull the 'reminder_lead_minutes' field. Lenient, same as
        reminder_phrase: any missing/invalid value falls back to 0 (fire
        exactly at due_at) rather than failing the whole parse. A lead time
        only makes sense with a due time, so it's forced to 0 when due_at
        is None regardless of what the LLM returned — mirrors the same
        clamp ChatService._create_commitments() already applies.
        """
        if due_at is None:
            return 0
        raw = parsed.get("reminder_lead_minutes")
        try:
            return max(0, min(1440, int(raw or 0)))
        except (ValueError, TypeError):
            logger.warning(f"LLM returned invalid reminder_lead_minutes, defaulting to 0: {raw!r}")
            return 0
