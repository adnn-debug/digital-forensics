"""Authentication Pydantic schemas."""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserRead


class TokenResponse(BaseModel):
    """JWT access token response returned on successful login."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds")
    user: UserRead


class LoginRequest(BaseModel):
    """Credentials payload for the login endpoint."""

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    model_config = ConfigDict(str_strip_whitespace=True)
