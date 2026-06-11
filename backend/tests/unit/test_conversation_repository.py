"""
test_conversation_repository.py — Unit tests for per-user chat history.
"""

from uuid import uuid4

from app.repositories.conversation_repository import ConversationRepository
from app.repositories.user_repository import UserRepository


def _make_user(db_connection, email="c@example.com"):
    """Create a user row (conversation_turns FKs to users). google_id is
    derived from the email so distinct users get distinct google_ids."""
    return UserRepository(db_connection).create(f"g-{email}", email, "C", None)


def test_recent_empty_when_no_turns(db_connection) -> None:
    repo = ConversationRepository(db_connection)
    assert repo.recent(uuid4()) == []


def test_append_then_recent_chronological(db_connection) -> None:
    user = _make_user(db_connection)
    repo = ConversationRepository(db_connection)

    repo.append(user.id, "user", "first")
    repo.append(user.id, "assistant", "second")
    repo.append(user.id, "user", "third")

    turns = repo.recent(user.id, limit=10)
    assert [t.content for t in turns] == ["first", "second", "third"]  # oldest-first
    assert [t.role for t in turns] == ["user", "assistant", "user"]


def test_recent_limit_returns_newest_in_order(db_connection) -> None:
    user = _make_user(db_connection)
    repo = ConversationRepository(db_connection)
    for i in range(5):
        repo.append(user.id, "user", f"m{i}")

    turns = repo.recent(user.id, limit=2)
    # The two newest, still oldest-first
    assert [t.content for t in turns] == ["m3", "m4"]


def test_history_is_scoped_per_user(db_connection) -> None:
    a = _make_user(db_connection, "a@example.com")
    b = _make_user(db_connection, "b@example.com")
    repo = ConversationRepository(db_connection)

    repo.append(a.id, "user", "a-secret")
    repo.append(b.id, "user", "b-secret")

    assert [t.content for t in repo.recent(a.id)] == ["a-secret"]
    assert [t.content for t in repo.recent(b.id)] == ["b-secret"]


def test_clear_removes_only_that_users_turns(db_connection) -> None:
    a = _make_user(db_connection, "a2@example.com")
    b = _make_user(db_connection, "b2@example.com")
    repo = ConversationRepository(db_connection)
    repo.append(a.id, "user", "x")
    repo.append(a.id, "assistant", "y")
    repo.append(b.id, "user", "z")

    removed = repo.clear(a.id)
    assert removed == 2
    assert repo.recent(a.id) == []
    assert [t.content for t in repo.recent(b.id)] == ["z"]  # B untouched
