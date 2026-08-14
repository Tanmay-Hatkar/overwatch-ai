"""
chat_service.py — The conversational chat router.

A single LLM call does TWO jobs:
  1. Classify intent (add_commitment | query | general)
  2. Generate a natural-language reply

For add_commitment, the LLM also extracts text + due_at and we persist
the new commitment before returning.

For query, the LLM is given the user's open + overdue commitments and
today's events as context. It answers from that data, never inventing.

For general, the LLM just chats. No DB writes.

Failure handling: if the LLM returns invalid JSON or is unavailable,
raise ChatError. The route turns this into a 503 with a user-readable
message.

Stale-plan check-in interception (ADR-0017): before any of the above,
handle() checks whether the user has a pending "still the plan?" check-in
(sent by StaleCheckScheduler, not yet acknowledged). If so, one small
dedicated LLM call classifies the reply and — for still_valid / abandon /
reschedule — returns immediately without running the normal pipeline. Only
'unrelated' falls through to the normal flow for that same message.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.agents.orchestrator import call_llm
from app.config import settings
from app.models.chat import (
    ChatRequest,
    ChatResponse,
    ChatTurn,
    _ChatIntentResult,
)
from app.models.commitment import (
    CommitmentCreate,
    CommitmentResponse,
    CommitmentStatus,
    CommitmentUpdate,
    Recurrence,
)
from app.models.stale_check import _StaleCheckReplyResult
from app.prompts.chat import SYSTEM_PROMPT, USER_TEMPLATE
from app.prompts.stale_check_reply import (
    SYSTEM_PROMPT as STALE_CHECK_SYSTEM_PROMPT,
    USER_TEMPLATE as STALE_CHECK_USER_TEMPLATE,
)
from app.repositories.conversation_repository import ConversationRepository
from app.services.calendar_service import CalendarService
from app.services.commitment_service import CommitmentService
from app.services.timezone_utils import resolve_timezone, to_user_date

logger = logging.getLogger(__name__)

_DAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]


class ChatError(Exception):
    """Raised when the LLM is unavailable or returns unparseable output."""


class ChatService:
    """
    Conversational router that turns user messages into actions + replies.

    Composes CommitmentService (so we can create commitments + read current
    state) and CalendarService (so query intents can mention meetings).
    """

    def __init__(
        self,
        commitment_service: CommitmentService,
        calendar_service: CalendarService | None = None,
        conversation_repo: ConversationRepository | None = None,
    ) -> None:
        self._service = commitment_service
        self._calendar = calendar_service
        # When present, conversation history is loaded from + persisted to the
        # database (server-side, cross-device) instead of relying solely on the
        # client-supplied history. Optional so existing tests/callers still work.
        self._conversation = conversation_repo

    def handle(self, user_id: UUID, request: ChatRequest) -> ChatResponse:
        """Process one chat message end-to-end, scoped to user_id."""
        user_tz = resolve_timezone(request.timezone)
        now_local = datetime.now(user_tz)

        # Stale-plan check-in interception (ADR-0017): if the user has any
        # pending "still the plan?" check-ins, the very next message is
        # treated as a reply to them first. Terminal outcomes short-circuit
        # the rest of handle(); 'unrelated' falls through below.
        pending = self._service.list_pending_stale_checks(user_id)
        if pending:
            intercepted = self._handle_stale_check_reply(user_id, request, now_local, user_tz, pending)
            if intercepted is not None:
                return intercepted

        # Prefer server-persisted history (follows the user across devices);
        # fall back to the client-supplied history when no repo is wired.
        if self._conversation is not None:
            history = self._conversation.recent(user_id, limit=10)
        else:
            history = request.history[-10:]

        user_prompt = self._build_user_prompt(user_id, request, now_local, user_tz, history)

        raw = call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=settings.llm_intent_temperature,
        )

        if raw is None:
            raise ChatError("LLM unavailable — no provider succeeded")

        result = self._parse_json(raw)

        commitment: CommitmentResponse | None = None
        if result.intent == "add_commitment":
            created = self._create_commitments(user_id, result, user_tz)
            # Return the first created record for the UI's toast; the client
            # refreshes its list afterward, so all created items appear.
            commitment = created[0] if created else None
        elif result.intent == "modify_commitment":
            commitment = self._modify_commitment(user_id, result, user_tz)

        # Persist this exchange so it's part of future context.
        if self._conversation is not None:
            self._conversation.append(user_id, "user", request.message)
            self._conversation.append(user_id, "assistant", result.reply)

        return ChatResponse(
            reply=result.reply,
            intent=result.intent,
            commitment=commitment,
            clarify_kind=result.clarify_kind if result.intent == "clarify" else None,
            clarify_options=result.clarify_options if result.intent == "clarify" else None,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_user_prompt(
        self,
        user_id: UUID,
        request: ChatRequest,
        now_local: datetime,
        user_tz: ZoneInfo,
        history: list[ChatTurn],
    ) -> str:
        """
        Build the user prompt. `now_local` is the current moment rendered in
        the user's timezone, so 'today', 'tonight', and the date table are all
        anchored to the user's wall clock rather than the server's. `history`
        is the recent conversation (DB-backed when available, else client-sent),
        oldest-first.
        """
        day_names = _DAY_NAMES
        date_table = self._build_date_lookup(now_local)

        # Current local clock time, e.g. "4:42 PM" — lets the LLM resolve
        # "in 30 minutes", "tonight at 7", "in an hour" correctly.
        now_time = now_local.strftime("%I:%M %p").lstrip("0")

        # Pull current state for query intent — scoped to this user.
        open_items = self._service.list(user_id, status=CommitmentStatus.OPEN)
        today_date = now_local.date()

        # due_at is stored UTC-aware; bucket and display it in the user's
        # timezone (to_user_date), not the server's/UTC — same reasoning as
        # BriefingService._bucket_commitments (ADR-0023 follow-up).
        today_open = [c for c in open_items if c.due_at and to_user_date(c.due_at, user_tz) == today_date]
        overdue = [c for c in open_items if c.due_at and to_user_date(c.due_at, user_tz) < today_date]

        open_list = self._format_commitment_list(today_open, user_tz) if today_open else "  (none)"
        overdue_list = self._format_commitment_list(overdue, user_tz) if overdue else "  (none)"
        # ALL open commitments (not just today/overdue) with their ids, so
        # modify_commitment can reference any of them, not just what's due soon.
        editable_list = (
            self._format_editable_list(open_items, user_tz) if open_items else "  (none)"
        )

        # Today's calendar events
        events_list = "  (none)"
        events_count = 0
        if self._calendar is not None:
            events = self._calendar.list_today(today_date)
            events_count = len(events)
            if events:
                lines = []
                for e in events:
                    time_str = e.start_at.astimezone(user_tz).strftime("%I:%M %p").lstrip("0")
                    lines.append(f"  - {time_str} {e.title}")
                events_list = "\n".join(lines)

        # Recent conversation — format each turn as "User: ..." / "Assistant: ..."
        if history:
            convo_lines = []
            for turn in history[-10:]:  # cap at last 10 turns
                speaker = "User" if turn.role == "user" else "Assistant"
                convo_lines.append(f"  {speaker}: {turn.content}")
            conversation = "\n".join(convo_lines)
        else:
            conversation = "  (no prior turns)"

        return USER_TEMPLATE.format(
            now_time=now_time,
            today_name=day_names[now_local.weekday()],
            today_date=now_local.date().isoformat(),
            date_table=date_table,
            open_count=len(today_open),
            open_list=open_list,
            overdue_count=len(overdue),
            overdue_list=overdue_list,
            editable_list=editable_list,
            events_count=events_count,
            events_list=events_list,
            conversation=conversation,
            message=request.message,
        )

    @staticmethod
    def _format_commitment_list(commitments: list[CommitmentResponse], user_tz: ZoneInfo) -> str:
        lines = []
        for c in commitments:
            if c.due_at:
                time_str = c.due_at.astimezone(user_tz).strftime("%I:%M %p").lstrip("0")
                lines.append(f"  - {c.text} (due {time_str})")
            else:
                lines.append(f"  - {c.text}")
        return "\n".join(lines)

    @staticmethod
    def _format_editable_list(commitments: list[CommitmentResponse], user_tz: ZoneInfo) -> str:
        """Every open commitment with its id, for modify_commitment to target.
        Unlike _format_commitment_list (today/overdue only), this covers ALL
        open commitments — an edit isn't limited to what's due soon."""
        lines = []
        for c in commitments:
            if c.due_at:
                dt_str = c.due_at.astimezone(user_tz).strftime("%Y-%m-%dT%H:%M:%S")
                rec = f", recurrence={c.recurrence.value}" if c.recurrence.value != "none" else ""
                lines.append(f'  - id={c.id} "{c.text}" due {dt_str}{rec}')
            else:
                rec = f", recurrence={c.recurrence.value}" if c.recurrence.value != "none" else ""
                lines.append(f'  - id={c.id} "{c.text}" (no due date){rec}')
        return "\n".join(lines)

    @staticmethod
    def _strip_code_fences(raw: str) -> str:
        """Strip a leading/trailing ```-fence, if present, from an LLM reply."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0]
        return cleaned

    @staticmethod
    def _parse_json(raw: str) -> _ChatIntentResult:
        """Strip markdown fences, parse JSON, validate against schema."""
        cleaned = ChatService._strip_code_fences(raw)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"Chat LLM returned non-JSON: {raw!r}")
            raise ChatError(f"LLM output was not valid JSON: {e}") from e

        try:
            return _ChatIntentResult(**data)
        except Exception as e:
            logger.warning(f"Chat LLM returned malformed structured output: {data!r}")
            raise ChatError(f"LLM output missing required fields: {e}") from e

    @staticmethod
    def _build_date_lookup(now_local: datetime) -> str:
        """14-day date lookup table (today + 13 more), same as the standalone parser (ADR 0003)."""
        lookup_lines = []
        for i in range(14):
            d = now_local + timedelta(days=i)
            marker = " (today)" if i == 0 else " (tomorrow)" if i == 1 else ""
            lookup_lines.append(f"  {d.date().isoformat()} — {_DAY_NAMES[d.weekday()]}{marker}")
        return "\n".join(lookup_lines)

    # ------------------------------------------------------------------
    # Stale-plan check-in interception (ADR-0017)
    # ------------------------------------------------------------------

    def _handle_stale_check_reply(
        self,
        user_id: UUID,
        request: ChatRequest,
        now_local: datetime,
        user_tz: ZoneInfo,
        pending: list[CommitmentResponse],
    ) -> ChatResponse | None:
        """
        Intercept the user's reply to one or more pending stale-plan check-ins.

        Runs one small dedicated LLM call to classify the reply, applies the
        outcome to every pending commitment, and acknowledges each so this
        interception fires at most once per check-in.

        Returns:
            A ChatResponse for a terminal outcome (still_valid / abandon /
            reschedule), or None when the LLM is unavailable, unparseable,
            or the outcome is 'unrelated' — in all of those cases the
            caller falls through to the normal chat pipeline for the same
            message.
        """
        user_prompt = self._build_stale_check_prompt(request.message, now_local, pending)

        raw = call_llm(
            system_prompt=STALE_CHECK_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=settings.llm_intent_temperature,
        )
        if raw is None:
            logger.warning("stale-check reply LLM unavailable; leaving check-ins pending")
            return None

        try:
            result = self._parse_stale_check_json(raw)
        except ChatError as e:
            logger.warning(f"stale-check reply parse failed: {e}; leaving check-ins pending")
            return None

        if result.outcome == "unrelated":
            for c in pending:
                self._service.acknowledge_stale_check(user_id, c.id)
            return None

        for c in pending:
            resolved = self._apply_stale_check_outcome(user_id, c, result, user_tz)
            if resolved:
                self._service.acknowledge_stale_check(user_id, c.id)
            # else: a reschedule with no extractable time is left pending
            # (not acknowledged) so the user's actual next reply gets a
            # real chance to give one, instead of the check-in silently
            # closing with due_at never having moved.

        if self._conversation is not None:
            self._conversation.append(user_id, "user", request.message)
            self._conversation.append(user_id, "assistant", result.reply)

        return ChatResponse(reply=result.reply, intent="general", commitment=None)

    def _apply_stale_check_outcome(
        self,
        user_id: UUID,
        commitment: CommitmentResponse,
        result: _StaleCheckReplyResult,
        user_tz: ZoneInfo,
    ) -> bool:
        """
        Apply a classified stale-check outcome to one pending commitment.

        still_valid: no state change. abandon: mark abandoned — a choice
        the user made, never framed as a failure. reschedule: move due_at
        if the LLM extracted a new time; never guess at a time the user
        didn't give.

        Returns:
            True if this outcome is resolved and the check-in should be
            acknowledged (still_valid, abandon, or reschedule-with-a-time).
            False for a reschedule with no extractable time — that's not
            resolved, just deferred: the caller must NOT acknowledge, so
            the user's next reply gets a real chance to supply one instead
            of the check-in silently closing with due_at never having
            moved (the prompt's reply text asks for the time explicitly
            in this case — see stale_check_reply.py).
        """
        if result.outcome == "abandon":
            self._service.update(
                user_id, commitment.id, CommitmentUpdate(status=CommitmentStatus.ABANDONED)
            )
            return True
        elif result.outcome == "reschedule":
            new_due = self._parse_due_at(result.new_due_at, user_tz)
            if new_due is not None:
                self._service.update(user_id, commitment.id, CommitmentUpdate(due_at=new_due))
                return True
            return False
        return True  # still_valid

    @staticmethod
    def _build_stale_check_prompt(
        message: str, now_local: datetime, pending: list[CommitmentResponse]
    ) -> str:
        """Build the user prompt for the stale-check reply classifier."""
        pending_list = "\n".join(f"  - {c.text}" for c in pending)
        return STALE_CHECK_USER_TEMPLATE.format(
            now_time=now_local.strftime("%I:%M %p").lstrip("0"),
            today_name=_DAY_NAMES[now_local.weekday()],
            today_date=now_local.date().isoformat(),
            date_table=ChatService._build_date_lookup(now_local),
            pending_list=pending_list,
            message=message,
        )

    @staticmethod
    def _parse_stale_check_json(raw: str) -> _StaleCheckReplyResult:
        """Strip markdown fences, parse JSON, validate against the stale-check schema."""
        cleaned = ChatService._strip_code_fences(raw)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"stale-check LLM returned non-JSON: {raw!r}")
            raise ChatError(f"stale-check LLM output was not valid JSON: {e}") from e

        try:
            return _StaleCheckReplyResult(**data)
        except Exception as e:
            logger.warning(f"stale-check LLM returned malformed structured output: {data!r}")
            raise ChatError(f"stale-check LLM output missing required fields: {e}") from e

    def _create_commitments(
        self, user_id: UUID, result: _ChatIntentResult, user_tz: ZoneInfo
    ) -> list[CommitmentResponse]:
        """
        For add_commitment intents, persist one OR many commitments.

        When the LLM returns `items` (multiple commitments in one message),
        each is created. Otherwise the single text/due_at pair is used. An
        item with empty text is skipped rather than failing the whole turn.

        Returns the created records (may be empty if nothing was usable).
        """
        # Normalize to a list of (text, due_str, recurrence, lead, phrase) drafts.
        if result.items:
            drafts = [
                (d.text, d.due_at, d.recurrence, d.reminder_lead_minutes, d.reminder_phrase)
                for d in result.items
            ]
        elif result.text:
            drafts = [
                (
                    result.text,
                    result.due_at,
                    result.recurrence,
                    result.reminder_lead_minutes,
                    result.reminder_phrase,
                )
            ]
        else:
            logger.warning("add_commitment intent had no text/items; skipping create")
            return []

        created: list[CommitmentResponse] = []
        for text_raw, due_raw, rec_raw, lead_raw, phrase_raw in drafts:
            text = (text_raw or "").strip()
            if not text:
                continue
            due_at = self._parse_due_at(due_raw, user_tz)
            # A lead time only makes sense with a due time; clamp to 0..1440.
            lead = max(0, min(1440, int(lead_raw or 0))) if due_at is not None else 0
            phrase = (phrase_raw or "").strip() or None
            payload = CommitmentCreate(
                text=text,
                due_at=due_at,
                recurrence=self._parse_recurrence(rec_raw),
                reminder_lead_minutes=lead,
                reminder_phrase=phrase,
            )
            created.append(self._service.create(user_id, payload))
        return created

    def _modify_commitment(
        self, user_id: UUID, result: _ChatIntentResult, user_tz: ZoneInfo
    ) -> CommitmentResponse | None:
        """
        For modify_commitment intents, apply only the field(s) the LLM
        actually returned to the target commitment. target_commitment_id
        must reference an open commitment the user owns — anything else
        (missing id, wrong user, id for a done/abandoned commitment) is
        treated as a no-op rather than raising, since a hallucinated or
        stale id shouldn't crash the turn.
        """
        if not result.target_commitment_id:
            logger.warning("modify_commitment intent had no target_commitment_id; skipping")
            return None

        try:
            target_id = UUID(result.target_commitment_id)
        except ValueError:
            logger.warning(f"modify_commitment returned a non-UUID id: {result.target_commitment_id!r}")
            return None

        existing = self._service.get(user_id, target_id)
        if existing is None or existing.status != CommitmentStatus.OPEN:
            logger.warning(f"modify_commitment target not found or not open: {target_id}")
            return None

        changes: dict = {}
        if result.text:
            changes["text"] = result.text.strip()
        if result.due_at:
            changes["due_at"] = self._parse_due_at(result.due_at, user_tz)
        if result.recurrence:
            changes["recurrence"] = self._parse_recurrence(result.recurrence)
        if result.reminder_lead_minutes is not None and (result.due_at or existing.due_at):
            changes["reminder_lead_minutes"] = max(0, min(1440, int(result.reminder_lead_minutes)))
        if result.reminder_phrase:
            changes["reminder_phrase"] = result.reminder_phrase.strip()

        if not changes:
            logger.warning(f"modify_commitment for {target_id} had no fields to change; skipping")
            return existing

        return self._service.update(user_id, target_id, CommitmentUpdate(**changes))

    @staticmethod
    def _parse_recurrence(value: str | None) -> Recurrence:
        """Map the LLM's recurrence string to the enum; default to NONE."""
        try:
            return Recurrence(value) if value else Recurrence.NONE
        except ValueError:
            return Recurrence.NONE

    @staticmethod
    def _parse_due_at(due_str: str | None, user_tz: ZoneInfo) -> datetime | None:
        """
        Convert an LLM-emitted due_at string to a tz-aware UTC datetime.

        The LLM emits a naive wall-clock time (no offset), meaning the time in
        the USER'S timezone. We attach the user's timezone, then convert to UTC
        so reminders fire at the right absolute instant and every device renders
        it in its own local time. Invalid values are dropped (returns None).

        A same-day relative phrase ("tonight", "in an hour") can resolve to an
        instant that's already passed by the time it gets here — e.g. no
        explicit rule for what "tonight" defaults to, or a plain LLM mistake.
        Since this product's whole model is a reminder firing at a real future
        moment, a past due_at is never useful and just leaves a commitment
        permanently "overdue" from the instant it's created. Clamp forward to
        "now" rather than silently accept it.
        """
        if not due_str:
            return None
        try:
            parsed = datetime.fromisoformat(due_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=user_tz)
            resolved = parsed.astimezone(UTC)
        except (ValueError, TypeError):
            logger.warning(f"chat: invalid due_at dropped: {due_str!r}")
            return None

        now = datetime.now(UTC)
        if resolved < now:
            logger.warning(
                f"chat: due_at {due_str!r} resolved to the past ({resolved.isoformat()}); "
                "clamping to now"
            )
            return now
        return resolved
