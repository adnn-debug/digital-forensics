"""Tests for centralized exception handling."""

import pytest
from httpx import AsyncClient

from app.core.exceptions import (
    IntegrityViolationException,
    ResourceNotFoundException,
    SecurityViolationException,
)
from app.main import app


@app.get("/test-not-found")
async def trigger_not_found() -> None:
    raise ResourceNotFoundException(resource_type="EvidenceItem", resource_id="evd-999")


@app.get("/test-integrity")
async def trigger_integrity_violation() -> None:
    raise IntegrityViolationException(
        evidence_id="evd-101",
        expected_hash="abc123",
        actual_hash="def456",
    )


@app.get("/test-security")
async def trigger_security_violation() -> None:
    raise SecurityViolationException(
        message="Command injection detected in metadata argument",
        vector="COMMAND_INJECTION",
    )


@pytest.mark.asyncio
async def test_resource_not_found_handling(async_client: AsyncClient) -> None:
    """Verify 404 translation with structured error JSON."""
    response = await async_client.get("/test-not-found")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert "evd-999" in data["error"]["message"]
    assert data["error"]["details"]["resource_type"] == "EvidenceItem"


@pytest.mark.asyncio
async def test_integrity_violation_handling(async_client: AsyncClient) -> None:
    """Verify 409 Conflict translation for forensic hash mismatch."""
    response = await async_client.get("/test-integrity")
    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "INTEGRITY_VIOLATION"
    assert data["error"]["details"]["expected_hash"] == "abc123"
    assert data["error"]["details"]["actual_hash"] == "def456"


@pytest.mark.asyncio
async def test_security_violation_handling(async_client: AsyncClient) -> None:
    """Verify 403 Forbidden translation for security violations."""
    response = await async_client.get("/test-security")
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "SECURITY_VIOLATION"
    assert data["error"]["details"]["vector"] == "COMMAND_INJECTION"
