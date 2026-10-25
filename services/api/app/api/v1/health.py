"""Health and readiness probe endpoints."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Response, status

from app.api.deps import check_redis_connectivity, get_storage
from app.core.config import get_settings
from app.db.session import check_db_connectivity

router = APIRouter(tags=["Health & Diagnostics"])


@router.get(
    "/health",
    summary="Liveness Probe",
    description="Returns HTTP 200 if the API service process is up and running.",
    status_code=status.HTTP_200_OK,
)
async def health_check() -> dict[str, Any]:
    """Liveness probe indicating the application process is alive."""
    settings = get_settings()
    return {
        "status": "OPERATIONAL",
        "service": "ps05-api",
        "version": "0.1.0",
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get(
    "/ready",
    summary="Readiness Probe",
    description="Tests active connectivity to PostgreSQL, Redis, and storage vaults.",
)
async def readiness_check(response: Response) -> dict[str, Any]:
    """
    Readiness probe testing essential downstream dependencies.

    Returns HTTP 200 when ready to receive traffic, or HTTP 503 if an essential
    subsystem is unavailable.
    """
    settings = get_settings()
    storage = get_storage()

    # Execute subsystem checks concurrently / sequentially
    db_health = await check_db_connectivity()
    redis_health = await check_redis_connectivity()
    storage_health = storage.check_storage_health()

    is_db_ready = db_health.get("status") == "HEALTHY"
    is_storage_ready = storage_health.get("status") == "HEALTHY"
    is_redis_ready = redis_health.get("status") == "HEALTHY"

    # Overall readiness evaluation
    all_ready = is_db_ready and is_storage_ready and is_redis_ready

    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "READY" if all_ready else "NOT_READY",
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(UTC).isoformat(),
        "subsystems": {
            "database": db_health,
            "redis": redis_health,
            "storage": storage_health,
        },
    }
