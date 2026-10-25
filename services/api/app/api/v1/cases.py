"""
Case management endpoints.

All routes require a valid JWT (CurrentUser). Create/update routes
additionally require ADMIN or EXAMINER roles.  Case-level authorization
is enforced on the backend — a user may only view their own cases unless
they are ADMIN or AUDITOR.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_roles
from app.core.security import compute_event_hash
from app.db.models.audit import AuditEventType
from app.db.models.case import CaseStatus
from app.db.models.user import UserRole
from app.repositories.audit_repo import AuditRepository
from app.repositories.case_repo import CaseRepository
from app.schemas.audit import AuditEventCreate
from app.schemas.case import CaseCreate, CaseRead, CaseUpdate
from app.schemas.pagination import PaginatedResponse

logger = logging.getLogger("ps05.cases")

router = APIRouter(prefix="/cases", tags=["Cases"])

# Maximum page size to prevent unbounded queries
_MAX_PAGE_SIZE = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_case_access(case_lead_id: UUID | None, current_user: Any) -> None:
    """
    Enforce case-level authorization.

    ADMIN and AUDITOR can view any case.
    EXAMINER / VIEWER can only access cases they lead.

    Raises HTTP 403 if the current user is not permitted.
    """
    if current_user.role in (UserRole.ADMIN.value, UserRole.AUDITOR.value):
        return  # Full access

    if case_lead_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "CASE_ACCESS_DENIED",
                "message": "You are not authorized to access this case.",
            },
        )


async def _append_case_audit(
    audit_repo: AuditRepository,
    db: AsyncSession,
    *,
    event_type: AuditEventType,
    action: str,
    case_id: UUID,
    user_id: UUID,
    previous_hash: str | None = None,
    delta: dict[str, Any] | None = None,
) -> str:
    """Create and persist an immutable audit event for a case action."""
    ts = datetime.now(UTC).isoformat()
    event_hash = compute_event_hash(
        event_type=event_type.value,
        action_description=action,
        user_id=str(user_id),
        case_id=str(case_id),
        previous_hash=previous_hash,
        timestamp=ts,
    )
    payload = AuditEventCreate(
        case_id=case_id,
        evidence_id=None,
        user_id=user_id,
        event_type=event_type,
        action_description=action,
        ip_address=None,
        user_agent=None,
        previous_state_hash=previous_hash,
        event_hash=event_hash,
        payload_delta=delta,
        timestamp=datetime.fromisoformat(ts),
    )
    await audit_repo.append_event(payload)
    return event_hash


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=CaseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new investigation case",
    dependencies=[require_roles(UserRole.ADMIN.value, UserRole.EXAMINER.value)],
)
async def create_case(
    payload: CaseCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """
    Create a new forensic investigation case.

    - Requires ADMIN or EXAMINER role.
    - Automatically assigns the creating user as lead investigator if none supplied.
    - Emits a CASE_STATUS_CHANGED audit event.
    """
    case_repo = CaseRepository(db)
    audit_repo = AuditRepository(db)

    # Ensure unique case number
    existing = await case_repo.get_by_case_number(payload.case_number)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DUPLICATE_CASE_NUMBER",
                "message": f"Case number '{payload.case_number}' already exists.",
            },
        )

    # Default lead investigator to the creating user
    if payload.lead_investigator_id is None:
        payload = payload.model_copy(update={"lead_investigator_id": current_user.id})

    case = await case_repo.create_case(payload)

    await _append_case_audit(
        audit_repo,
        db,
        event_type=AuditEventType.CASE_STATUS_CHANGED,
        action=f"Case '{case.case_number}' created by {current_user.email}",
        case_id=case.id,
        user_id=current_user.id,
        delta={"status": case.status, "title": case.title},
    )
    await db.commit()

    logger.info("Case %s created by %s", case.case_number, current_user.email)
    return CaseRead.model_validate(case)


@router.get(
    "",
    response_model=PaginatedResponse[CaseRead],
    summary="List investigation cases",
)
async def list_cases(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: CaseStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=20, ge=1, le=_MAX_PAGE_SIZE, description="Items per page"),
) -> Any:
    """
    Return a paginated list of cases.

    - ADMIN / AUDITOR see all cases.
    - EXAMINER / VIEWER see only cases they lead.
    """
    from sqlalchemy import func, select

    from app.db.models.case import Case

    offset = (page - 1) * page_size

    is_privileged = current_user.role in (UserRole.ADMIN.value, UserRole.AUDITOR.value)

    # Build base query — unprivileged users are scoped to their own cases
    base_stmt = select(Case)
    if not is_privileged:
        base_stmt = base_stmt.where(Case.lead_investigator_id == current_user.id)
    if status_filter is not None:
        base_stmt = base_stmt.where(Case.status == status_filter.value)

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total: int = (await db.execute(count_stmt)).scalar_one()

    list_stmt = base_stmt.order_by(Case.created_at.desc()).offset(offset).limit(page_size)
    rows = (await db.execute(list_stmt)).scalars().all()

    return PaginatedResponse(
        items=[CaseRead.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.get(
    "/{case_id}",
    response_model=CaseRead,
    summary="Get case details",
)
async def get_case(
    case_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """
    Retrieve full details of a single case.

    Enforces case-level authorization on the backend — EXAMINER/VIEWER
    can only view their own cases.
    """
    case_repo = CaseRepository(db)
    case = await case_repo.get_by_id(case_id)

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CASE_NOT_FOUND", "message": f"Case '{case_id}' not found."},
        )

    _assert_case_access(case.lead_investigator_id, current_user)

    return CaseRead.model_validate(case)


@router.patch(
    "/{case_id}",
    response_model=CaseRead,
    summary="Update case metadata or status",
    dependencies=[require_roles(UserRole.ADMIN.value, UserRole.EXAMINER.value)],
)
async def update_case(
    case_id: UUID,
    payload: CaseUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """
    Partially update a case's title, description, status, or lead investigator.

    - Requires ADMIN or EXAMINER role.
    - EXAMINER may only update their own cases (enforced backend).
    - Emits a CASE_STATUS_CHANGED audit event.
    """
    case_repo = CaseRepository(db)
    audit_repo = AuditRepository(db)

    case = await case_repo.get_by_id(case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CASE_NOT_FOUND", "message": f"Case '{case_id}' not found."},
        )

    _assert_case_access(case.lead_investigator_id, current_user)

    # Record previous state for audit delta
    previous_state = {
        "status": case.status,
        "title": case.title,
        "description": case.description,
    }

    # Fetch previous hash for chain continuity
    latest_event = await audit_repo.get_latest_event_for_case(case_id)
    previous_hash = latest_event.event_hash if latest_event else None

    updated_case = await case_repo.update_case(case, payload)

    new_state = {
        "status": updated_case.status,
        "title": updated_case.title,
        "description": updated_case.description,
    }

    await _append_case_audit(
        audit_repo,
        db,
        event_type=AuditEventType.CASE_STATUS_CHANGED,
        action=f"Case '{case.case_number}' updated by {current_user.email}",
        case_id=case.id,
        user_id=current_user.id,
        previous_hash=previous_hash,
        delta={"before": previous_state, "after": new_state},
    )
    await db.commit()

    logger.info("Case %s updated by %s", case.case_number, current_user.email)
    return CaseRead.model_validate(updated_case)
