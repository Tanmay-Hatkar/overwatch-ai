"""
user.py — Pydantic models for the User entity.

A User row is created the first time someone signs in with Google.
google_id (the immutable "sub" claim from Google's id_token) is the
foreign identifier; our own UUID is the primary key everywhere else
in the system.

Email can change on the Google side (rare, but possible — corporate
migrations, marriage, etc.), so we never use email as a key. Always
use the UUID.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserResponse(BaseModel):
    """Public representation of a user — safe to send to the frontend."""

    id: UUID = Field(description="Internal stable identifier")
    email: EmailStr = Field(description="User's email address from Google")
    name: str = Field(description="Display name from Google profile")
    picture: str | None = Field(default=None, description="Profile picture URL")
    created_at: datetime = Field(description="When the user first signed in")
    last_login_at: datetime = Field(description="Most recent /auth/me success")


class GoogleUserInfo(BaseModel):
    """
    Decoded payload from a Google id_token.

    Only the fields we use are listed; google's id_token has many more
    (aud, iss, exp, etc.) which we validate via the google-auth library
    but don't store.
    """

    sub: str = Field(description="Google's immutable user ID (becomes google_id)")
    email: EmailStr
    name: str
    picture: str | None = None
    email_verified: bool = Field(
        default=True,
        description=(
            "Whether Google has verified the email. We reject sign-ins from "
            "unverified addresses to prevent spoofing."
        ),
    )
