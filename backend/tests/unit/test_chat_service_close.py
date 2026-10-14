"""
test_chat_service_close.py — ChatService's close_commitment intent (ADR-0027).

The LLM is mocked at the chat_service import site, as in test_chat_service.py.
Covers done / abandoned / deleted, multi-target closes, the single-id
fallback, user scoping, the per-message cap, and the honest fallback reply
when nothing could be closed.
"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.config import settings
from app.models.chat import ChatRequest
from app.models.commitment import CommitmentCreate, CommitmentStatus, CommitmentUpdate, Recurrence
from app.services.chat_service import ChatService
from app.services.commitment_service import CommitmentService

LLM_PATCH = "app.services.chat_service.call_llm"

UID = uuid4()


@pytest.fixture
def chat(service: CommitmentService) -> ChatService:
    return ChatService(service)


def _llm(**fields) -> str:
    return json.dumps({"intent": "close_commitment", "reply": "llm reply", **fields})


def _say(chat: ChatService, message: str):
    return chat.handle(UID, ChatRequest(message=message, timezone="UTC"))


def _make(service: CommitmentService, text: str, **kwargs):
    return service.create(UID, CommitmentCreate(text=text, **kwargs))


def test_close_done_marks_commitment_done(chat: ChatService, service: CommitmentService) -> None:
    c = _make(service, "Call mom")
    with patch(LLM_PATCH, return_value=_llm(target_commitment_ids=[str(c.id)], close_action="done")):
        response = _say(chat, "just called mom")

    assert response.intent == "close_commitment"
    assert response.close_action == "done"
    assert [x.id for x in response.closed] == [c.id]
    assert response.reply == "llm reply"
    assert service.get(UID, c.id).status == CommitmentStatus.DONE


def test_close_abandoned_marks_commitment_abandoned(
    chat: ChatService, service: CommitmentService
) -> None:
    c = _make(service, "Dentist")
    with patch(LLM_PATCH, return_value=_llm(target_commitment_ids=[str(c.id)], close_action="abandoned")):
        response = _say(chat, "never mind the dentist")

    assert response.close_action == "abandoned"
    assert service.get(UID, c.id).status == CommitmentStatus.ABANDONED


def test_close_deleted_removes_every_named_commitment(
    chat: ChatService, service: CommitmentService
) -> None:
    a = _make(service, "Do laundry")
    b = _make(service, "Hit the gym")
    keep = _make(service, "Call mom")
    fake = _llm(target_commitment_ids=[str(a.id), str(b.id)], close_action="deleted")
    with patch(LLM_PATCH, return_value=fake):
        response = _say(chat, "delete the laundry and the gym ones")

    assert response.close_action == "deleted"
    assert {x.text for x in response.closed} == {"Do laundry", "Hit the gym"}
    assert service.get(UID, a.id) is None
    assert service.get(UID, b.id) is None
    assert service.get(UID, keep.id) is not None


def test_close_done_on_recurring_rolls_forward(chat: ChatService, service: CommitmentService) -> None:
    due = datetime.now(UTC) + timedelta(hours=1)
    c = _make(service, "Night routine", due_at=due, recurrence=Recurrence.DAILY)
    with patch(LLM_PATCH, return_value=_llm(target_commitment_ids=[str(c.id)], close_action="done")):
        _say(chat, "did my night routine")

    after = service.get(UID, c.id)
    assert after.status == CommitmentStatus.OPEN
    assert after.due_at > due


def test_close_accepts_single_target_commitment_id(
    chat: ChatService, service: CommitmentService
) -> None:
    """Models sometimes reuse modify_commitment's single-id field."""
    c = _make(service, "Call mom")
    with patch(LLM_PATCH, return_value=_llm(target_commitment_id=str(c.id), close_action="deleted")):
        response = _say(chat, "delete call mom")

    assert [x.id for x in response.closed] == [c.id]
    assert service.get(UID, c.id) is None


def test_close_skips_bad_ids_but_applies_good_ones(
    chat: ChatService, service: CommitmentService
) -> None:
    c = _make(service, "Call mom")
    ids = ["not-a-uuid", str(uuid4()), str(c.id), str(c.id)]
    with patch(LLM_PATCH, return_value=_llm(target_commitment_ids=ids, close_action="deleted")):
        response = _say(chat, "delete call mom")

    assert [x.id for x in response.closed] == [c.id]


def test_close_cannot_touch_another_users_commitment(
    chat: ChatService, service: CommitmentService
) -> None:
    other = uuid4()
    c = service.create(other, CommitmentCreate(text="Someone else's task"))
    with patch(LLM_PATCH, return_value=_llm(target_commitment_ids=[str(c.id)], close_action="deleted")):
        response = _say(chat, "delete that")

    assert response.closed is None
    assert service.get(other, c.id) is not None


def test_close_ignores_already_closed_commitment(
    chat: ChatService, service: CommitmentService
) -> None:
    c = _make(service, "Finish the deck")
    service.update(UID, c.id, CommitmentUpdate(status=CommitmentStatus.DONE))
    with patch(LLM_PATCH, return_value=_llm(target_commitment_ids=[str(c.id)], close_action="deleted")):
        response = _say(chat, "delete the deck")

    assert response.closed is None
    assert service.get(UID, c.id) is not None


@pytest.mark.parametrize(
    "fields",
    [
        {"target_commitment_ids": [], "close_action": "deleted"},
        {"target_commitment_ids": None, "close_action": "done"},
        {"target_commitment_ids": [str(uuid4())], "close_action": "deleted"},
    ],
)
def test_close_with_nothing_applicable_replaces_reply(chat: ChatService, fields: dict) -> None:
    with patch(LLM_PATCH, return_value=_llm(**fields)):
        response = _say(chat, "delete it")

    assert response.closed is None
    assert response.close_action is None
    assert response.reply == ChatService._close_fallback_reply()


def test_close_without_action_changes_nothing(chat: ChatService, service: CommitmentService) -> None:
    c = _make(service, "Call mom")
    with patch(LLM_PATCH, return_value=_llm(target_commitment_ids=[str(c.id)])):
        response = _say(chat, "call mom")

    assert response.closed is None
    assert service.get(UID, c.id).status == CommitmentStatus.OPEN


def test_close_is_capped_per_message(
    chat: ChatService, service: CommitmentService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "chat_max_close_targets", 2)
    made = [_make(service, f"Task {i}") for i in range(3)]
    fake = _llm(target_commitment_ids=[str(c.id) for c in made], close_action="deleted")
    with patch(LLM_PATCH, return_value=fake):
        response = _say(chat, "delete everything")

    assert len(response.closed) == 2
    assert len(service.list(UID, status=CommitmentStatus.OPEN)) == 1


def test_close_fields_absent_on_other_intents(chat: ChatService) -> None:
    fake = json.dumps({"intent": "general", "reply": "hey", "close_action": "deleted"})
    with patch(LLM_PATCH, return_value=fake):
        response = _say(chat, "hey")

    assert response.closed is None
    assert response.close_action is None


def test_prompt_offers_ids_for_close(chat: ChatService, service: CommitmentService) -> None:
    c = _make(service, "Call mom")
    with patch(LLM_PATCH, return_value=json.dumps({"intent": "general", "reply": "ok"})) as mock:
        _say(chat, "delete call mom")

    user_prompt = mock.call_args.kwargs["user_prompt"]
    assert f'id={c.id} "Call mom"' in user_prompt
    assert "close_commitment" in user_prompt
