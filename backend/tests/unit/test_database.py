"""
test_database.py — Unit tests for the SQLite connection helper.

Covers the cross-thread connection bug fixed by check_same_thread=False
in get_connection(): FastAPI runs sync path operations and their
yield-based dependencies via anyio's worker threadpool, which doesn't
guarantee a get_db() generator's setup and its post-request conn.close()
teardown land on the same OS thread under concurrent load — reproduced
live via the ~6 parallel requests the frontend fires on every app launch,
which intermittently 500'd with "SQLite objects created in a thread can
only be used in that same thread."
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app.database import get_connection


def test_connection_usable_from_a_different_thread(tmp_path: Path) -> None:
    """A connection created in one thread must be queryable and closable
    from a different thread without raising sqlite3.ProgrammingError."""
    db_path = tmp_path / "test.db"

    with patch("app.database._resolve_db_path", return_value=db_path):
        conn = get_connection()

    def use_from_other_thread() -> None:
        conn.execute("SELECT 1").fetchone()
        conn.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(use_from_other_thread)
        future.result()  # re-raises any exception that happened in the thread
