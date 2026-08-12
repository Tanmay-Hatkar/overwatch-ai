"""
runner.py — Executes eval cases against the REAL LLM (no mocking) and
scores the results.

This is the harness named in the AI-foundation plan's phase A1: it exists
because every existing unit test mocks call_llm, so nothing has ever
measured whether the actual prompts (backend/app/prompts/{chat,
commitment_parser}.py), given real varied phrasing, produce correct
output. See cases.yaml for the case format.

Two dispatch pipelines, matching Overwatch's two capture surfaces:
  parse — CommitmentParserService.parse_and_create() (POST /commitments/parse)
  chat  — ChatService.handle() (POST /chat)

Each case pins "now" via a real datetime subclass with `now()` overridden
(NOT a bare MagicMock — that would break every other datetime method the
pipeline calls, like fromisoformat) so results are reproducible
regardless of when the eval is actually run.

This module has no pytest dependency — it's importable and runnable both
from test_extraction_eval.py (pytest, mocked-out by nothing, real calls)
and from scripts/run_eval.py (a plain CLI script).
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime as real_datetime
from pathlib import Path
from typing import Any, Literal
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import yaml

from app.agents.orchestrator import call_llm
from app.config import settings
from app.migrations import run_migrations
from app.models.chat import ChatRequest
from app.providers.mock_calendar_provider import MockCalendarProvider
from app.repositories.commitment_repository import CommitmentRepository
from app.services.calendar_service import CalendarService
from app.services.chat_service import ChatService
from app.services.commitment_parser_service import CommitmentParserService
from app.services.commitment_service import CommitmentService

CASES_PATH = Path(__file__).parent / "cases.yaml"

_JUDGE_SYSTEM_PROMPT = (
    "You are grading whether a reminder phrase meets a rubric. Reply with "
    "ONLY valid JSON: {\"pass\": true|false, \"reason\": \"...\"}. Be strict "
    "but fair -- the phrase does not need to match any exact wording, only "
    "the spirit of the rubric."
)


@dataclass
class CaseResult:
    id: str
    category: str
    pipeline: str
    passed: bool
    checks: list[str] = field(default_factory=list)
    error: str | None = None


def _frozen_datetime(fixed_now: real_datetime) -> type[real_datetime]:
    """
    A real datetime subclass with now() pinned, so date arithmetic,
    fromisoformat, strftime etc. all still work exactly like the real
    class -- only now() is overridden. A bare MagicMock would silently
    break every other datetime call the pipeline makes.
    """

    class _Frozen(real_datetime):
        @classmethod
        def now(cls, tz: ZoneInfo | None = None) -> real_datetime:
            return fixed_now.astimezone(tz) if tz is not None else fixed_now

    return _Frozen


def _fresh_service() -> CommitmentService:
    """A CommitmentService backed by a throwaway in-memory database."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    return CommitmentService(CommitmentRepository(conn))


def load_cases() -> list[dict[str, Any]]:
    with open(CASES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["cases"]


def _parse_fixed_now(case: dict[str, Any]) -> real_datetime:
    naive = real_datetime.fromisoformat(case["now"])
    return naive.replace(tzinfo=ZoneInfo(case.get("timezone") or "UTC"))


def _run_parse_pipeline(case: dict[str, Any]) -> tuple[Any, str | None]:
    service = _fresh_service()
    parser = CommitmentParserService(service)
    fixed_now = _parse_fixed_now(case)
    try:
        with patch(
            "app.services.commitment_parser_service.datetime",
            _frozen_datetime(fixed_now),
        ):
            result = parser.parse_and_create(uuid4(), case["message"], case.get("timezone"))
        return result, None
    except Exception as e:  # noqa: BLE001 -- eval harness must never crash the batch
        return None, str(e)


def _run_chat_pipeline(case: dict[str, Any]) -> tuple[Any, str | None]:
    service = _fresh_service()
    chat_service = ChatService(service, CalendarService(MockCalendarProvider()))
    fixed_now = _parse_fixed_now(case)
    try:
        with patch("app.services.chat_service.datetime", _frozen_datetime(fixed_now)):
            request = ChatRequest(
                message=case["message"], history=[], timezone=case.get("timezone")
            )
            result = chat_service.handle(uuid4(), request)
        return result, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def judge_reminder_phrase(rubric: str, message: str, phrase: str | None) -> tuple[bool, str]:
    """Real LLM-as-judge call for a subjective field. Never mocked -- this
    is the whole point of the harness."""
    if not phrase:
        return False, "reminder_phrase was empty/None"
    user_prompt = (
        f"Original message: {message!r}\n"
        f"Rubric: {rubric}\n"
        f"Reminder phrase to grade: {phrase!r}\n\n"
        "Reply with JSON only."
    )
    raw = call_llm(
        system_prompt=_JUDGE_SYSTEM_PROMPT, user_prompt=user_prompt, temperature=0.0
    )
    if raw is None:
        return False, "judge LLM unavailable"
    try:
        import json

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0]
        data = json.loads(cleaned)
        return bool(data["pass"]), str(data.get("reason", ""))
    except Exception as e:  # noqa: BLE001
        return False, f"judge output unparseable: {e} (raw={raw!r})"


def _to_local(due_at: Any, tz: ZoneInfo) -> Any:
    """
    Normalize due_at to the case's local wall-clock time before comparing
    date/time components.

    The two pipelines store due_at differently: CommitmentParserService
    persists the LLM's naive local value as-is (no conversion), while
    ChatService._parse_due_at deliberately attaches the user's timezone
    and converts to UTC before persisting (so reminders fire at the
    right absolute instant). Comparing a chat-pipeline due_at's raw
    strftime() against an expected LOCAL time would silently compare
    against UTC instead -- this normalizes both cases the same way.
    """
    if due_at is None:
        return None
    if due_at.tzinfo is None:
        return due_at.replace(tzinfo=tz)
    return due_at.astimezone(tz)


def _score_commitment_fields(
    checks: list[str],
    expect: dict[str, Any],
    text: str | None,
    due_at: Any,
    tz: ZoneInfo,
    reminder_lead_minutes: int | None = None,
) -> bool:
    ok = True
    due_at = _to_local(due_at, tz)

    if "reminder_lead_minutes" in expect:
        if reminder_lead_minutes == expect["reminder_lead_minutes"]:
            checks.append(f"PASS reminder_lead_minutes ({reminder_lead_minutes})")
        else:
            checks.append(
                f"FAIL reminder_lead_minutes: expected {expect['reminder_lead_minutes']}, "
                f"got {reminder_lead_minutes}"
            )
            ok = False

    if "due_at_null" in expect:
        if expect["due_at_null"]:
            if due_at is not None:
                checks.append(f"FAIL due_at_null: expected None, got {due_at}")
                ok = False
            else:
                checks.append("PASS due_at_null")

    if "due_at_date" in expect:
        got = due_at.date().isoformat() if due_at is not None else None
        if got == expect["due_at_date"]:
            checks.append(f"PASS due_at_date ({got})")
        else:
            checks.append(f"FAIL due_at_date: expected {expect['due_at_date']}, got {got}")
            ok = False

    if "due_at_time" in expect:
        got = due_at.strftime("%H:%M") if due_at is not None else None
        if got == expect["due_at_time"]:
            checks.append(f"PASS due_at_time ({got})")
        else:
            checks.append(f"FAIL due_at_time: expected {expect['due_at_time']}, got {got}")
            ok = False

    if "text_contains" in expect:
        haystack = (text or "").lower()
        for needle in expect["text_contains"]:
            if needle.lower() in haystack:
                checks.append(f"PASS text_contains {needle!r}")
            else:
                checks.append(f"FAIL text_contains: {needle!r} not in {text!r}")
                ok = False

    if "text_not_contains" in expect:
        haystack = (text or "").lower()
        for needle in expect["text_not_contains"]:
            if needle.lower() not in haystack:
                checks.append(f"PASS text_not_contains {needle!r}")
            else:
                checks.append(f"FAIL text_not_contains: {needle!r} found in {text!r}")
                ok = False

    return ok


def run_case(case: dict[str, Any]) -> CaseResult:
    pipeline: Literal["parse", "chat"] = case["pipeline"]
    checks: list[str] = []
    tz = ZoneInfo(case.get("timezone") or "UTC")

    if pipeline == "parse":
        commitment, error = _run_parse_pipeline(case)
        if error is not None:
            return CaseResult(case["id"], case["category"], pipeline, False, error=error)
        text = commitment.text
        due_at = commitment.due_at
        ok = _score_commitment_fields(
            checks, case["expect"], text, due_at, tz, commitment.reminder_lead_minutes
        )
        if "reminder_phrase_judge" in case["expect"]:
            passed, reason = judge_reminder_phrase(
                case["expect"]["reminder_phrase_judge"], case["message"], commitment.reminder_phrase
            )
            checks.append(f"{'PASS' if passed else 'FAIL'} reminder_phrase_judge: {reason}")
            ok = ok and passed
        return CaseResult(case["id"], case["category"], pipeline, ok, checks)

    elif pipeline == "chat":
        response, error = _run_chat_pipeline(case)
        if error is not None:
            return CaseResult(case["id"], case["category"], pipeline, False, error=error)
        ok = True
        expect = case["expect"]

        if "intent" in expect:
            if response.intent == expect["intent"]:
                checks.append(f"PASS intent ({response.intent})")
            else:
                checks.append(f"FAIL intent: expected {expect['intent']}, got {response.intent}")
                ok = False

        commitment = response.commitment
        text = commitment.text if commitment else None
        due_at = commitment.due_at if commitment else None
        ok = _score_commitment_fields(checks, expect, text, due_at, tz) and ok

        if "recurrence" in expect:
            got = commitment.recurrence.value if commitment else None
            if got == expect["recurrence"]:
                checks.append(f"PASS recurrence ({got})")
            else:
                checks.append(f"FAIL recurrence: expected {expect['recurrence']}, got {got}")
                ok = False

        return CaseResult(case["id"], case["category"], pipeline, ok, checks)

    raise ValueError(f"unknown pipeline: {pipeline!r}")


def run_all(cases: list[dict[str, Any]] | None = None) -> list[CaseResult]:
    if cases is None:
        cases = load_cases()
    return [run_case(c) for c in cases]


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    by_category: dict[str, list[CaseResult]] = {}
    for r in results:
        by_category.setdefault(r.category, []).append(r)

    category_summary = {
        cat: {
            "passed": sum(1 for r in rs if r.passed),
            "total": len(rs),
        }
        for cat, rs in by_category.items()
    }
    total_passed = sum(1 for r in results if r.passed)
    return {
        "total_passed": total_passed,
        "total": len(results),
        "pass_rate": total_passed / len(results) if results else 0.0,
        "by_category": category_summary,
    }


def require_openai_configured() -> None:
    """Fail loudly and early rather than silently scoring every case as a
    failure because no provider was configured."""
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set -- the eval harness makes real LLM "
            "calls and needs at least one provider configured. See backend/.env."
        )
