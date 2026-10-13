"""
test_chat_service_goals.py — ChatService's weekly-goal intents (ADR-0026).

The LLM is mocked at the chat_service import site, as in test_chat_service.py.
Covers add_goal (create + re-target), log_goal, the "Weekly goals" prompt
context, and the honest fallback reply when a goal intent can't be applied.
"""

import json
import sqlite3
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.models.chat import ChatRequest
from app.models.goal import GoalCreate
from app.models.user import UserResponse
from app.repositories.goal_repository import GoalRepository
from app.services.chat_service import ChatService
from app.services.commitment_service import CommitmentService
from app.services.goal_service import GoalService

LLM_PATCH = "app.services.chat_service.call_llm"
UTC_TZ = ZoneInfo("UTC")


@pytest.fixture
def goal_service(db_connection: sqlite3.Connection) -> GoalService:
    return GoalService(GoalRepository(db_connection))


@pytest.fixture
def chat(service: CommitmentService, goal_service: GoalService) -> ChatService:
    return ChatService(service, goal_service=goal_service)


def _llm(intent: str, **fields) -> str:
    return json.dumps({"intent": intent, "reply": "llm reply", **fields})


def _say(chat: ChatService, user: UserResponse, message: str):
    return chat.handle(user.id, ChatRequest(message=message, timezone="UTC"))


def test_add_goal_creates_goal(
    chat: ChatService, goal_service: GoalService, test_user: UserResponse
) -> None:
    fake = _llm("add_goal", goal_text="Job applications", target_count=10)
    with patch(LLM_PATCH, return_value=fake):
        response = _say(chat, test_user, "10 job applications this week")
    assert response.intent == "add_goal"
    assert response.goal is not None
    assert response.goal.text == "Job applications"
    assert response.goal.target_count == 10
    assert response.reply == "llm reply"
    assert len(goal_service.list(test_user.id, UTC_TZ)) == 1


def test_add_goal_with_existing_id_retargets_instead_of_duplicating(
    chat: ChatService, goal_service: GoalService, test_user: UserResponse
) -> None:
    existing = goal_service.create(test_user.id, GoalCreate(text="Gym", target_count=3), UTC_TZ)
    fake = _llm("add_goal", goal_text="Gym", target_count=5, target_goal_id=str(existing.id))
    with patch(LLM_PATCH, return_value=fake):
        response = _say(chat, test_user, "make gym 5 a week")
    assert response.goal is not None
    assert response.goal.id == existing.id
    assert response.goal.target_count == 5
    assert len(goal_service.list(test_user.id, UTC_TZ)) == 1


@pytest.mark.parametrize("bad", [None, 0, 1000])
def test_add_goal_with_unusable_count_falls_back(
    chat: ChatService, goal_service: GoalService, test_user: UserResponse, bad: int | None
) -> None:
    fake = _llm("add_goal", goal_text="Gym", target_count=bad)
    with patch(LLM_PATCH, return_value=fake):
        response = _say(chat, test_user, "gym a lot")
    assert response.goal is None
    assert "how many times a week" in response.reply
    assert goal_service.list(test_user.id, UTC_TZ) == []


def test_add_goal_without_text_falls_back(chat: ChatService, test_user: UserResponse) -> None:
    with patch(LLM_PATCH, return_value=_llm("add_goal", target_count=4)):
        response = _say(chat, test_user, "4 a week")
    assert response.goal is None


def test_log_goal_adds_progress(
    chat: ChatService, goal_service: GoalService, test_user: UserResponse
) -> None:
    g = goal_service.create(test_user.id, GoalCreate(text="Job applications", target_count=10), UTC_TZ)
    fake = _llm("log_goal", target_goal_id=str(g.id), amount=2)
    with patch(LLM_PATCH, return_value=fake):
        response = _say(chat, test_user, "applied to 2 more")
    assert response.goal is not None
    assert response.goal.done_this_week == 2


def test_log_goal_amount_defaults_and_clamps(
    chat: ChatService, goal_service: GoalService, test_user: UserResponse
) -> None:
    g = goal_service.create(test_user.id, GoalCreate(text="Gym", target_count=4), UTC_TZ)
    with patch(LLM_PATCH, return_value=_llm("log_goal", target_goal_id=str(g.id))):
        assert _say(chat, test_user, "went to the gym").goal.done_this_week == 1
    with patch(LLM_PATCH, return_value=_llm("log_goal", target_goal_id=str(g.id), amount=-5)):
        assert _say(chat, test_user, "gym again").goal.done_this_week == 2


@pytest.mark.parametrize("bad_id", [None, "not-a-uuid", str(uuid4())])
def test_log_goal_with_bad_id_replies_honestly(
    chat: ChatService, test_user: UserResponse, bad_id: str | None
) -> None:
    with patch(LLM_PATCH, return_value=_llm("log_goal", target_goal_id=bad_id, amount=1)):
        response = _say(chat, test_user, "did one")
    assert response.goal is None
    assert "which one" in response.reply


def test_goal_intent_without_goal_service_is_honest(
    service: CommitmentService, test_user: UserResponse
) -> None:
    bare = ChatService(service)
    with patch(LLM_PATCH, return_value=_llm("add_goal", goal_text="Gym", target_count=3)):
        response = _say(bare, test_user, "gym 3x a week")
    assert response.goal is None
    assert response.reply != "llm reply"


def test_prompt_lists_goals_with_progress(
    chat: ChatService, goal_service: GoalService, test_user: UserResponse
) -> None:
    g = goal_service.create(test_user.id, GoalCreate(text="Job applications", target_count=10), UTC_TZ)
    goal_service.log(test_user.id, g.id, 3, UTC_TZ)
    with patch(LLM_PATCH, return_value=_llm("general")) as mock_llm:
        _say(chat, test_user, "how am I doing?")
    prompt = mock_llm.call_args.kwargs["user_prompt"]
    assert f'id={g.id} "Job applications" 3 of 10 this week' in prompt


def test_prompt_says_none_without_goals(chat: ChatService, test_user: UserResponse) -> None:
    with patch(LLM_PATCH, return_value=_llm("general")) as mock_llm:
        _say(chat, test_user, "hey")
    prompt = mock_llm.call_args.kwargs["user_prompt"]
    assert "Weekly goals (for add_goal/log_goal/query" in prompt
    assert prompt.split("Weekly goals")[1].split("\n")[1].strip() == "(none)"
