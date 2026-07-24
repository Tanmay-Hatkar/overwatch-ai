"""
backfill_reminder_phrases.py — One-time backfill of reminder_phrase for
existing open commitments (ADR-0021, migration 011_reminder_phrase.sql).

Commitments created before reminder_phrase existed have it as NULL, and
never get it since the field is only ever set at parse time going forward.
This script fills it in for currently-open commitments across every user,
via ReminderPhraseBackfillService (one narrow LLM call per commitment,
text/due_at held fixed as given context — never re-derived, so this can
never alter an existing due date or task text).

Idempotent: only commitments where reminder_phrase IS NULL are touched, so
re-running after a partial failure (e.g. LLM provider hiccup) only retries
what's still missing.

Requires the same environment as the running backend (DATABASE_PATH and at
least one of OPENAI_API_KEY / GROQ_API_KEY / an Ollama instance reachable
at OLLAMA_BASE_URL — see backend/.env.example). This script does not read
or need any secret beyond what the backend already uses.

Run (from backend/, with the same .env the app uses):
  python scripts/backfill_reminder_phrases.py
"""

import sys

from app.database import get_connection
from app.repositories.commitment_repository import CommitmentRepository
from app.repositories.user_repository import UserRepository
from app.services.commitment_service import CommitmentService
from app.services.reminder_phrase_backfill_service import ReminderPhraseBackfillService


def main() -> int:
    conn = get_connection()
    try:
        commitment_service = CommitmentService(CommitmentRepository(conn))
        backfill_service = ReminderPhraseBackfillService(commitment_service)
        user_ids = UserRepository(conn).list_all_ids()

        if not user_ids:
            print("No users found — nothing to backfill.")
            return 0

        total_updated = 0
        total_skipped = 0
        for user_id in user_ids:
            updated, skipped = backfill_service.backfill_user(user_id)
            total_updated += updated
            total_skipped += skipped
            if updated or skipped:
                print(f"user {user_id}: {updated} updated, {skipped} skipped")

        print(f"\nDone. {total_updated} commitments updated, {total_skipped} skipped.")
        if total_skipped:
            print("Skipped rows had an LLM failure or invalid response — re-run this "
                  "script to retry them (only rows still missing reminder_phrase are touched).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
