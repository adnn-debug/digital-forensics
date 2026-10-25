"""Health and readiness probe endpoints with sanitized public diagnostics."""

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


def _public_dependency_status(result: dict[str, Any]) -> dict[str, Any]:
    """Expose only safe health fields; never return connection strings, paths, or exception text."""
    safe: dict[str, Any] = {"status": result.get("status", "UNHEALTHY")}
    latency = result.get("latency_ms")
    if isinstance(latency, (int, float)):
        safe["latency_ms"] = latency
    return safe


@router.get(
    "/ready",
    summary="Readiness Probe",
    description="Tests active connectivity to PostgreSQL, Redis, and storage vaults.",
)
async def readiness_check(response: Response) -> dict[str, Any]:
    """Return safe subsystem statuses and HTTP 503 when a required dependency is unavailable."""
    settings = get_settings()
    storage = get_storage()

    db_health = await check_db_connectivity()
    redis_health = await check_redis_connectivity()
    storage_health = storage.check_storage_health()

    db_public = _public_dependency_status(db_health)
    redis_public = _public_dependency_status(redis_health)
    storage_public = {
        "status": storage_health.get("status", "UNHEALTHY"),
        "directories": {
            name: {"status": info.get("status", "UNHEALTHY")}
            for name, info in storage_health.get("directories", {}).items()
        },
    }

    all_ready = all(
        item.get("status") == "HEALTHY"
        for item in (db_public, redis_public, storage_public)
    )
    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "READY" if all_ready else "NOT_READY",
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(UTC).isoformat(),
        "subsystems": {
            "database": db_public,
            "redis": redis_public,
            "storage": storage_public,
        },
    }
