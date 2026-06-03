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
from app.models.chat import ChatRequest, ChatResponse
from app.repositories.commitment_repository import CommitmentRepository
from app.routes.calendar import get_calendar_service
from app.services.calendar_service import CalendarService
from app.services.chat_service import ChatError, ChatService
from app.services.commitment_service import CommitmentService

router = APIRouter(prefix="/chat", tags=["chat"])


def _build_chat_service(
    conn: sqlite3.Connection = Depends(get_db),
    calendar_service: CalendarService = Depends(get_calendar_service),
) -> ChatService:
    """Construct a ChatService for one request."""
    commitment_repo = CommitmentRepository(conn)
    commitment_service = CommitmentService(commitment_repo)
    return ChatService(commitment_service, calendar_service)


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    service: ChatService = Depends(_build_chat_service),
) -> ChatResponse:
    """Handle one conversational message and return the assistant's reply."""
    try:
        return service.handle(payload)
    except ChatError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chat failed: {e}",
        )
