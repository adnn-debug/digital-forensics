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


def _request_ip(request: Request) -> str | None:
    """Return the direct peer IP; do not trust spoofable X-Forwarded-For headers."""
    return request.client.host if request.client else None


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
    """Authenticate credentials and append a typed LOGIN audit event."""
    user_repo = UserRepository(db)
    audit_repo = AuditRepository(db)
    user = await user_repo.get_by_email(payload.email.lower().strip())

    # Verify even when the account does not exist to reduce timing-based account discovery.
    dummy_hash = "$2b$12$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    password_ok = verify_password(payload.password, user.hashed_password if user else dummy_hash)

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
    timestamp = datetime.now(UTC)
    previous = await audit_repo.get_latest_event()
    previous_hash = previous.event_hash if previous else None
    ip_address = _request_ip(request)
    action = f"User {user.id} authenticated successfully"

    event_hash = compute_event_hash(
        event_type=AuditEventType.LOGIN.value,
        action_description=action,
        user_id=str(user.id),
        case_id=None,
        previous_hash=previous_hash,
        timestamp=timestamp.isoformat(),
    )
    await audit_repo.append_event(
        AuditEventCreate(
            user_id=user.id,
            case_id=None,
            evidence_id=None,
            event_type=AuditEventType.LOGIN,
            action_description=action,
            ip_address=ip_address,
            user_agent=request.headers.get("user-agent"),
            previous_state_hash=previous_hash,
            event_hash=event_hash,
            payload_delta={"action": "LOGIN"},
            timestamp=timestamp,
        )
    )
    await db.commit()

    logger.info("User %s logged in from %s", user.id, ip_address or "unknown")
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserRead.model_validate(user),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Record logout for the current session",
    response_model=None,
)
async def logout(
    current_user: CurrentUser,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Append a typed LOGOUT audit event; token revocation is handled separately."""
    audit_repo = AuditRepository(db)
    timestamp = datetime.now(UTC)
    previous = await audit_repo.get_latest_event()
    previous_hash = previous.event_hash if previous else None
    action = f"User {current_user.id} logged out"
    event_hash = compute_event_hash(
        event_type=AuditEventType.LOGOUT.value,
        action_description=action,
        user_id=str(current_user.id),
        case_id=None,
        previous_hash=previous_hash,
        timestamp=timestamp.isoformat(),
    )
    await audit_repo.append_event(
        AuditEventCreate(
            user_id=current_user.id,
            case_id=None,
            evidence_id=None,
            event_type=AuditEventType.LOGOUT,
            action_description=action,
            ip_address=_request_ip(request),
            user_agent=request.headers.get("user-agent"),
            previous_state_hash=previous_hash,
            event_hash=event_hash,
            payload_delta={"action": "LOGOUT"},
            timestamp=timestamp,
        )
    )
    await db.commit()
    logger.info("User %s logged out", current_user.id)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Return the current authenticated user's profile",
)
async def get_me(current_user: CurrentUser) -> Any:
    """Return the authenticated user's profile — useful for bootstrapping the frontend."""
    return UserRead.model_validate(current_user)
