"""
setup_google_oauth.py — One-time interactive OAuth flow for Google Calendar.

Run this ONCE after placing your `credentials.json` in `backend/`. The
script will:

  1. Read credentials.json
  2. Open your browser to Google's consent screen
  3. Wait for you to grant access
  4. Save the resulting token to `token.json`

After that, the GoogleCalendarProvider will pick up the token
automatically and start serving real Calendar data. No further OAuth
interaction is needed — google-auth refreshes the access token in the
background when it expires.

Prerequisites (in Google Cloud Console):
  - Create a project
  - Enable "Google Calendar API"
  - Configure OAuth consent screen as "External" / "Testing"
  - Add your own Google account to "Test users"
  - Create OAuth Client ID, type "Desktop application"
  - Download the JSON; save as `backend/credentials.json`

Run:
  cd backend
  python scripts/setup_google_oauth.py
"""

import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

# Match the scopes the GoogleCalendarProvider requests, which match v1's
# token (so the existing token.json from v1 can be reused without a
# second OAuth flow).
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def main() -> int:
    # Default paths: backend/ working directory
    creds_path = Path("credentials.json")
    token_path = Path("token.json")

    if not creds_path.exists():
        print(
            "ERROR: credentials.json not found in current directory.\n"
            "\n"
            "Place your OAuth Client ID JSON (downloaded from Google Cloud Console)\n"
            "in backend/credentials.json, then re-run this script from the\n"
            "backend/ directory.",
            file=sys.stderr,
        )
        return 1

    if token_path.exists():
        print(
            f"WARNING: {token_path} already exists. Continuing will overwrite it.\n"
            "Press Ctrl+C to abort, or Enter to overwrite.",
            file=sys.stderr,
        )
        try:
            input()
        except KeyboardInterrupt:
            print("\nAborted.", file=sys.stderr)
            return 1

    print("Starting OAuth flow. Your browser will open in a moment.")
    print("After you approve, this script will save token.json and exit.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)

    token_path.write_text(creds.to_json())
    print(f"Saved {token_path}.")
    print("Done. The app will now use your real Google Calendar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
