"""Authentication endpoints — login, logout, and current-user profile."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    compute_event_hash,
    create_access_token,
    verify_password,
)
from app.db.models.audit import AuditEventType
from app.repositories.audit_repo import AuditRepository
from app.repositories.user_repo import UserRepository
from app.schemas.audit import AuditEventCreate
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserRead

logger = logging.getLogger("ps05.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and obtain a JWT access token",
)
async def login(
    payload: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """
    Exchange valid credentials for a signed JWT access token.

    - Normalises the email before lookup.
    - Uses bcrypt constant-time comparison — never leaks which field was wrong.
    - Records a LOGIN audit event on success.
    """
    user_repo = UserRepository(db)
    audit_repo = AuditRepository(db)

    # Normalise email before lookup to prevent case-confusion attacks
    user = await user_repo.get_by_email(payload.email.lower().strip())

    # Constant-time path: always verify even if user is None (prevents timing oracle)
    dummy_hash = "$2b$12$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    stored_hash = user.hashed_password if user else dummy_hash
    password_ok = verify_password(payload.password, stored_hash)

    if not user or not password_ok or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_CREDENTIALS",
                "message": "Invalid credentials provided.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(subject=user.id, role=user.role)

    # Append an immutable login audit event
    ts = datetime.now(UTC).isoformat()
    event_hash = compute_event_hash(
        event_type=AuditEventType.CASE_STATUS_CHANGED.value,  # closest generic type
        action_description=f"User {user.email} authenticated successfully",
        user_id=str(user.id),
        case_id=None,
        previous_hash=None,
        timestamp=ts,
    )
    audit_event = AuditEventCreate(
        user_id=user.id,
        case_id=None,
        evidence_id=None,
        event_type=AuditEventType.CASE_STATUS_CHANGED,
        action_description=f"User {user.email} authenticated from {request.client.host if request.client else 'unknown'}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        previous_state_hash=None,
        event_hash=event_hash,
        payload_delta={"action": "LOGIN"},
    )
    await audit_repo.append_event(audit_event)
    await db.commit()

    logger.info("User %s logged in from %s", user.email, request.client.host if request.client else "unknown")

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserRead.model_validate(user),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Invalidate the current session (client-side token drop)",
    response_model=None,
)
async def logout(current_user: CurrentUser) -> None:
    """
    Logout endpoint.

    Because we use stateless JWTs the server instructs the client to
    discard the token.  For full revocation a token-blocklist approach
    (stored in Redis) would be added in a later phase.
    """
    logger.info("User %s logged out", current_user.email)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Return the current authenticated user's profile",
)
async def get_me(current_user: CurrentUser) -> Any:
    """Return the authenticated user's profile — useful for bootstrapping the frontend."""
    return UserRead.model_validate(current_user)
