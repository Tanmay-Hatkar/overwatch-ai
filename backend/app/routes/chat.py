"""
chat.py — Conversational chat endpoint.

  POST /chat
       Body: { "message": str, "history": [ChatTurn] }
       Returns: { "reply": str, "intent": str, "commitment": CommitmentResponse? }

The LLM classifies the message as add_commitment, query, or general and
returns a natural-language reply. For add_commitment, a new commitment is
created server-side before the response returns; the created record is
included in the response so the UI can update without a separate fetch.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.models.chat import ChatRequest, ChatResponse, ChatTurn
from app.models.user import UserResponse
from app.repositories.commitment_repository import CommitmentRepository
from app.repositories.conversation_repository import ConversationRepository
from app.routes.auth import current_user
from app.routes.calendar import get_calendar_service
from app.services.calendar_service import CalendarService
from app.services.chat_service import ChatError, ChatService
from app.services.commitment_service import CommitmentService

router = APIRouter(prefix="/chat", tags=["chat"])


def _build_chat_service(
    conn: sqlite3.Connection = Depends(get_db),
    calendar_service: CalendarService = Depends(get_calendar_service),
) -> ChatService:
    """Construct a ChatService for one request, with DB-backed conversation memory."""
    commitment_service = CommitmentService(CommitmentRepository(conn))
    conversation_repo = ConversationRepository(conn)
    return ChatService(commitment_service, calendar_service, conversation_repo)


def _build_conversation_repo(
    conn: sqlite3.Connection = Depends(get_db),
) -> ConversationRepository:
    """Construct a ConversationRepository for the history endpoints."""
    return ConversationRepository(conn)


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    user: UserResponse = Depends(current_user),
    service: ChatService = Depends(_build_chat_service),
) -> ChatResponse:
    """Handle one conversational message and return the assistant's reply."""
    try:
        return service.handle(user.id, payload)
    except ChatError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chat failed: {e}",
        )


@router.get("/history", response_model=list[ChatTurn])
def get_history(
    limit: int = 50,
    user: UserResponse = Depends(current_user),
    repo: ConversationRepository = Depends(_build_conversation_repo),
) -> list[ChatTurn]:
    """Return the signed-in user's recent conversation turns (oldest first)."""
    return repo.recent(user.id, limit=limit)


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(
    user: UserResponse = Depends(current_user),
    repo: ConversationRepository = Depends(_build_conversation_repo),
) -> None:
    """Delete all of the signed-in user's conversation history."""
    repo.clear(user.id)
