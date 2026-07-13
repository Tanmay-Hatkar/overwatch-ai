"""
test_reminder_phrase_backfill_service.py — Unit tests for
ReminderPhraseBackfillService (ADR-0021).

The LLM is mocked via unittest.mock.patch, mirroring
test_commitment_parser_service.py's strategy. The service is wired to a
REAL CommitmentService (the `service` fixture from conftest), so a
successful backfill is verified end-to-end (read back from the DB).
"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from app.models.commitment import CommitmentCreate, CommitmentStatus, CommitmentUpdate
from app.services.commitment_service import CommitmentService
from app.services.reminder_phrase_backfill_service import ReminderPhraseBackfillService

LLM_PATCH_TARGET = "app.services.reminder_phrase_backfill_service.call_llm"

UID = uuid4()


def test_backfills_only_commitments_missing_reminder_phrase(service: CommitmentService) -> None:
    """Commitments that already have a reminder_phrase are left untouched."""
    already_set = service.create(
        UID, CommitmentCreate(text="Already has one", reminder_phrase="Existing phrase")
    )
    missing = service.create(UID, CommitmentCreate(text="Needs one"))

    fake = json.dumps({"reminder_phrase": "You said you'd needs one — did it happen?"})
    with patch(LLM_PATCH_TARGET, return_value=fake) as mock_llm:
        backfill = ReminderPhraseBackfillService(service)
        updated, skipped = backfill.backfill_user(UID)

    mock_llm.assert_called_once()  # only the missing one triggers an LLM call
    assert updated == 1
    assert skipped == 0

    refreshed_already_set = service.get(UID, already_set.id)
    refreshed_missing = service.get(UID, missing.id)
    assert refreshed_already_set.reminder_phrase == "Existing phrase"
    assert refreshed_missing.reminder_phrase == "You said you'd needs one — did it happen?"


def test_backfill_does_not_touch_text_or_due_at(service: CommitmentService) -> None:
    """The backfill only ever writes reminder_phrase — text/due_at are untouched."""
    due = datetime.now(UTC) + timedelta(days=1)
    created = service.create(UID, CommitmentCreate(text="Submit report", due_at=due))

    fake = json.dumps({"reminder_phrase": "You said you'd submit the report — done yet?"})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        ReminderPhraseBackfillService(service).backfill_user(UID)

    refreshed = service.get(UID, created.id)
    assert refreshed.text == "Submit report"
    assert refreshed.due_at == due


def test_skips_and_does_not_raise_when_llm_unavailable(service: CommitmentService) -> None:
    """LLM failure is skipped, not raised — the run continues for other users/commitments."""
    service.create(UID, CommitmentCreate(text="Needs one"))

    with patch(LLM_PATCH_TARGET, return_value=None):
        updated, skipped = ReminderPhraseBackfillService(service).backfill_user(UID)

    assert updated == 0
    assert skipped == 1


def test_skips_when_llm_returns_invalid_json(service: CommitmentService) -> None:
    """Malformed LLM output is skipped, not raised."""
    service.create(UID, CommitmentCreate(text="Needs one"))

    with patch(LLM_PATCH_TARGET, return_value="not json"):
        updated, skipped = ReminderPhraseBackfillService(service).backfill_user(UID)

    assert updated == 0
    assert skipped == 1


def test_ignores_done_commitments(service: CommitmentService) -> None:
    """Only OPEN commitments are candidates — done/abandoned ones are left alone."""
    created = service.create(UID, CommitmentCreate(text="Finished already"))
    service.update(UID, created.id, CommitmentUpdate(status=CommitmentStatus.DONE))

    with patch(LLM_PATCH_TARGET) as mock_llm:
        updated, skipped = ReminderPhraseBackfillService(service).backfill_user(UID)

    mock_llm.assert_not_called()
    assert updated == 0
    assert skipped == 0
