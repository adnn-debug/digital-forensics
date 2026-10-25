"""Authentication endpoints — login, logout, and current-user profile."""

from __future__ import annotations

import hashlib
import logging
import math
from datetime import UTC, datetime
from typing import Annotated, Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, get_redis_pool
from app.core.config import get_settings
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    compute_event_hash,
    create_access_token,
    decode_access_token,
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


async def _enforce_login_rate_limit(request: Request, email: str) -> None:
    """Limit repeated login attempts by both source IP and normalized account."""
    if get_settings().ENVIRONMENT == "testing":
        return

    ip = _request_ip(request) or "unknown"
    ip_digest = hashlib.sha256(ip.encode("utf-8")).hexdigest()
    email_digest = hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()
    client = aioredis.Redis(connection_pool=get_redis_pool())
    try:
        ip_key = f"ps05:login:ip:{ip_digest}"
        account_key = f"ps05:login:account:{email_digest}"
        # Increment both counters and assign their TTLs atomically so a Redis
        # interruption cannot leave a counter permanently locked without expiry.
        script = """
        local ip_count = redis.call('INCR', KEYS[1])
        if ip_count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
        local account_count = redis.call('INCR', KEYS[2])
        if account_count == 1 then redis.call('EXPIRE', KEYS[2], ARGV[1]) end
        return {ip_count, account_count}
        """
        counts = await client.eval(script, 2, ip_key, account_key, 900)
        ip_count, account_count = int(counts[1]), int(counts[2])
    except Exception as exc:
        logger.error("Login rate-limit store unavailable (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "AUTH_SERVICE_UNAVAILABLE", "message": "Authentication is temporarily unavailable."},
        ) from None
    finally:
        await client.close()

    if ip_count > 60 or account_count > 10:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "LOGIN_RATE_LIMITED", "message": "Too many login attempts. Try again later."},
            headers={"Retry-After": "900"},
        )


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
    normalized_email = payload.email.lower().strip()
    await _enforce_login_rate_limit(request, normalized_email)

    user_repo = UserRepository(db)
    audit_repo = AuditRepository(db)
    user = await user_repo.get_by_email(normalized_email)

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
    previous = await audit_repo.get_latest_auth_event()
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
    """Revoke the presented JWT and append a typed LOGOUT audit event."""
    settings = get_settings()
    authorization = request.headers.get("authorization", "")
    scheme, _, raw_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "Bearer token is required."},
        )

    token_payload = decode_access_token(raw_token)
    jti = token_payload.get("jti")
    expires_at = token_payload.get("exp")
    if settings.ENVIRONMENT != "testing":
        if not jti or not isinstance(expires_at, (int, float)):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_TOKEN", "message": "This session cannot be revoked safely."},
            )
        ttl = max(1, math.ceil(float(expires_at) - datetime.now(UTC).timestamp()))
        redis_client = aioredis.Redis(connection_pool=get_redis_pool())
        try:
            await redis_client.set(f"ps05:revoked:{jti}", "1", ex=ttl)
        except Exception as exc:
            logger.error("Session revocation store unavailable (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "AUTH_SERVICE_UNAVAILABLE", "message": "Logout could not be completed safely."},
            ) from None
        finally:
            await redis_client.close()

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
