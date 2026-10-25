"""Tests for health and readiness probes."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_liveness_endpoints(async_client: AsyncClient) -> None:
    """Verify that both /health and /api/v1/health return HTTP 200 with operational status."""
    for path in ("/health", "/api/v1/health"):
        response = await async_client.get(path)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "OPERATIONAL"
        assert data["service"] == "ps05-api"
        assert data["version"] == "0.1.0"
        assert "timestamp" in data
        assert "X-Process-Time-MS" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.asyncio
async def test_readiness_probe_healthy(async_client: AsyncClient) -> None:
    """Verify that readiness probe returns HTTP 200 when all subsystems report healthy."""
    with (
        patch("app.api.v1.health.check_db_connectivity", new_callable=AsyncMock) as mock_db,
        patch("app.api.v1.health.check_redis_connectivity", new_callable=AsyncMock) as mock_redis,
    ):
        mock_db.return_value = {"status": "HEALTHY", "latency_ms": 1.2, "database": "sqlite"}
        mock_redis.return_value = {"status": "HEALTHY", "latency_ms": 0.8}

        response = await async_client.get("/api/v1/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "READY"
        assert data["subsystems"]["database"]["status"] == "HEALTHY"
        assert data["subsystems"]["redis"]["status"] == "HEALTHY"
        assert data["subsystems"]["storage"]["status"] == "HEALTHY"


@pytest.mark.asyncio
async def test_readiness_probe_unhealthy(async_client: AsyncClient) -> None:
    """Verify that readiness probe returns HTTP 503 when a downstream service is down."""
    with (
        patch("app.api.v1.health.check_db_connectivity", new_callable=AsyncMock) as mock_db,
        patch("app.api.v1.health.check_redis_connectivity", new_callable=AsyncMock) as mock_redis,
    ):
        mock_db.return_value = {"status": "UNHEALTHY", "error": "Connection refused"}
        mock_redis.return_value = {"status": "HEALTHY", "latency_ms": 0.8}

        response = await async_client.get("/api/v1/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "NOT_READY"
        assert data["subsystems"]["database"]["status"] == "UNHEALTHY"
