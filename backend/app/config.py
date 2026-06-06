"""
config.py — Application configuration loaded from environment variables.

Uses pydantic-settings to load .env + OS env vars into a type-checked
Settings object. Other modules import `settings` and reference fields
directly — no more scattered os.getenv() calls.

If a required variable is missing or malformed, the app fails fast at
import time with a clear validation error. This is better than crashing
mid-request later.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All app settings, loaded from .env and OS environment."""

    # =========================================================================
    # LLM providers — fallback chain: OpenAI -> Groq -> Ollama
    # =========================================================================
    openai_api_key: str = Field(default="", description="OpenAI API key (empty disables provider)")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model identifier")

    groq_api_key: str = Field(default="", description="Groq API key (empty disables provider)")
    groq_model: str = Field(default="llama-3.1-8b-instant", description="Groq model identifier")

    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama HTTP base URL")
    ollama_model: str = Field(default="llama3.2", description="Ollama model identifier")

    # =========================================================================
    # LLM behavior
    # =========================================================================
    llm_temperature: float = Field(default=0.7, description="Default temperature for creative tasks")
    llm_intent_temperature: float = Field(default=0.0, description="Temperature for structured output")
    llm_max_tokens: int = Field(default=500, description="Maximum tokens per response")

    # =========================================================================
    # Web Push notifications (VAPID)
    # =========================================================================
    vapid_public_key: str = Field(default="", description="VAPID public key (base64url)")
    vapid_private_key: str = Field(default="", description="VAPID private key (base64url, secret)")
    vapid_subject: str = Field(
        default="mailto:admin@example.com",
        description="VAPID subject (mailto: URL identifying the app)",
    )
    reminder_poll_interval_seconds: int = Field(
        default=60,
        description="How often the reminder scheduler checks for newly-overdue commitments",
    )

    # =========================================================================
    # Authentication (Google OAuth + JWT sessions)
    # =========================================================================
    google_client_id: str = Field(
        default="",
        description="Google OAuth 2.0 client ID (from GCP console)",
    )
    google_client_secret: str = Field(
        default="",
        description="Google OAuth 2.0 client secret (from GCP console, keep secret)",
    )
    session_secret: str = Field(
        default="",
        description="HS256 signing key for JWT session cookies (32+ random chars)",
    )
    session_cookie_name: str = Field(
        default="ow_session",
        description="Name of the cookie that stores the JWT session",
    )
    session_max_age_days: int = Field(
        default=30,
        description="JWT expiry window. Refreshed when within session_refresh_within_days of expiry.",
    )
    session_refresh_within_days: int = Field(
        default=7,
        description="If a JWT is within this many days of expiry, /auth/me re-issues a fresh one.",
    )
    backend_url: str = Field(
        default="http://localhost:8000",
        description="Public URL of this backend (used to build the OAuth redirect_uri)",
    )
    frontend_url: str = Field(
        default="http://localhost:5173",
        description="Public URL of the frontend (used for post-login redirect + CORS)",
    )
    environment: str = Field(
        default="development",
        description="One of: development | production. Drives cookie Secure flag, log format.",
    )

    # =========================================================================
    # Production hardening
    # =========================================================================
    # Comma-separated list of origins allowed to call the API (browser CORS).
    # In dev, defaults to the Vite server. In prod, set to the Vercel URL.
    # Multiple origins: "https://overwatch.vercel.app,https://overwatch.dev"
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:5174",
        description="Comma-separated origins allowed for CORS",
    )

    # Comma-separated email allowlist for sign-in. If non-empty, only these
    # Google accounts can sign up/in. Empty string (default) = open signup.
    # For a single-user private deploy, set this to your email only.
    allowed_google_emails: str = Field(
        default="",
        description="Comma-separated email allowlist for sign-in (empty = open)",
    )

    # Absolute path to the SQLite DB file. Defaults to backend/data/overwatch.db
    # for local dev. In production set to e.g. /data/overwatch.db (Railway
    # volume mount point) so the DB survives container restarts.
    database_path: str = Field(
        default="",
        description="Absolute path to SQLite DB file (empty = backend/data/overwatch.db)",
    )

    # Log level: DEBUG | INFO | WARNING | ERROR. Defaults to INFO.
    log_level: str = Field(
        default="INFO",
        description="Python logging level",
    )

    # =========================================================================
    # Loader config
    # =========================================================================
    # env_file: load from backend/.env (relative to where uvicorn runs)
    # extra="ignore": ignore unrecognized env vars (don't crash on stray ones)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,  # OPENAI_API_KEY in env -> openai_api_key in Python
    )


# Singleton instance. Import this everywhere: `from app.config import settings`
settings = Settings()


def cors_origin_list() -> list[str]:
    """
    Parse settings.cors_origins (comma-separated) into a clean list.

    Trims whitespace, drops empty entries. Returns the list FastAPI's
    CORSMiddleware expects in `allow_origins`.
    """
    return [o.strip() for o in settings.cors_origins.split(",") if o.strip()]


def allowed_google_email_list() -> list[str]:
    """
    Parse settings.allowed_google_emails (comma-separated, lowercased).

    Empty list means "no allowlist" — anyone with a Google account can sign in.
    Non-empty list means "only these exact emails can sign in."
    """
    return [
        e.strip().lower()
        for e in settings.allowed_google_emails.split(",")
        if e.strip()
    ]


def is_email_allowed(email: str) -> bool:
    """
    Check whether the given email is permitted to sign in.

    Returns True when:
      - The allowlist is empty (open signup), OR
      - The (lowercased) email matches an entry in the allowlist.
    """
    allowlist = allowed_google_email_list()
    if not allowlist:
        return True
    return email.lower() in allowlist
