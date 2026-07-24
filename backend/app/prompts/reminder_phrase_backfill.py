"""
reminder_phrase_backfill.py — Prompt template for the one-time
reminder_phrase backfill (ADR-0021, backend/scripts/backfill_reminder_phrases.py).

Unlike commitment_parser.py, this does NOT parse natural language — it takes
an EXISTING commitment's already-correct `text`/`due_at` and asks only for
the reminder_phrase, so a backfill run can never accidentally change a
working due date. Kept as its own prompt module (matching this project's
one-file-per-prompt convention under app/prompts/) rather than reusing
commitment_parser.py's combined prompt.
"""

SYSTEM_PROMPT = (
    "You generate a reminder_phrase for an existing Overwatch commitment. "
    "You are given its text and due date (already correct — do NOT change "
    "or reinterpret them). Produce ONE field:\n"
    "\n"
    "  reminder_phrase: a natural, specific-recall check-in line (≤120 characters)\n"
    "\n"
    "Reply with ONLY valid JSON. No markdown, no explanation, no extra text.\n"
    "\n"
    "Format:\n"
    "{\"reminder_phrase\": \"...\"}\n"
    "\n"
    "Rules:\n"
    "- This is what the user hears/reads AT reminder time — it must sound like a "
    "considerate person recalling what they said, not a robot echoing a task name.\n"
    "- If a due time is given: reference it and frame it as a question, e.g. "
    "\"You said you'd start interview prep at 2:30 — starting?\"\n"
    "- If no due time is given: frame it as a check-in without a time, e.g. "
    "\"You said you'd hit today's gym session — did it happen?\"\n"
    "- Always start from \"You said you'd\" (or a natural equivalent) — this is "
    "recall, never a command or a judgment.\n"
    "- Concise: trim to ≤120 characters if needed.\n"
    "\n"
    "Examples:\n"
    "\n"
    "Commitment text: \"Call mom\"; due_at: \"2026-05-17T15:00:00\"\n"
    "Output: {\"reminder_phrase\": \"You said you'd call mom at 3pm — calling now?\"}\n"
    "\n"
    "Commitment text: \"Hit the gym\"; due_at: null\n"
    "Output: {\"reminder_phrase\": \"You said you'd hit today's gym session — did it happen?\"}\n"
)

USER_TEMPLATE = (
    "Commitment text: \"{text}\"\n"
    "due_at: {due_at}\n"
    "\n"
    "Return JSON only."
)
