"""Centralized domain exceptions and standardized HTTP exception handlers."""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("ps05.exceptions")


class PS05Exception(Exception):
    """Base exception for all PS-05 platform errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}


class ResourceNotFoundException(PS05Exception):
    """Raised when a case, evidence item, or report is not found."""

    def __init__(self, resource_type: str, resource_id: str) -> None:
        super().__init__(
            message=f"{resource_type} with ID '{resource_id}' was not found.",
            error_code="RESOURCE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource_type": resource_type, "resource_id": resource_id},
        )


class IntegrityViolationException(PS05Exception):
    """Critical exception raised when evidence hash validation fails (tamper detection)."""

    def __init__(self, evidence_id: str, expected_hash: str, actual_hash: str) -> None:
        super().__init__(
            message=f"Cryptographic hash integrity violation for evidence '{evidence_id}'.",
            error_code="INTEGRITY_VIOLATION",
            status_code=status.HTTP_409_CONFLICT,
            details={
                "evidence_id": evidence_id,
                "expected_hash": expected_hash,
                "actual_hash": actual_hash,
            },
        )


class StorageException(PS05Exception):
    """Raised when a storage I/O or permission error occurs."""

    def __init__(self, message: str, path: str | None = None) -> None:
        super().__init__(
            message=message,
            error_code="STORAGE_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"path": path} if path else {},
        )


class SecurityViolationException(PS05Exception):
    """Raised on unauthorized path traversal, command injection, or privilege violations."""

    def __init__(self, message: str, vector: str = "GENERAL") -> None:
        super().__init__(
            message=message,
            error_code="SECURITY_VIOLATION",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"vector": vector},
        )


def create_error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Format consistent error response across all API endpoints."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": error_code,
                "message": message,
                "details": details or {},
                "timestamp": datetime.now(UTC).isoformat(),
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all centralized exception handlers on the FastAPI application."""

    @app.exception_handler(PS05Exception)
    async def handle_ps05_exception(request: Request, exc: PS05Exception) -> JSONResponse:
        logger.warning(
            "PS05Exception occurred: code=%s message=%s path=%s",
            exc.error_code,
            exc.message,
            request.url.path,
        )
        return create_error_response(
            status_code=exc.status_code,
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.info("Validation error on path=%s: %s", request.url.path, exc.errors())
        return create_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            message="Request input validation failed.",
            details={"errors": exc.errors()},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        error_code = "HTTP_ERROR"
        message = str(exc.detail)
        details: dict[str, Any] = {"path": request.url.path}
        detail_obj = exc.detail
        if isinstance(exc.detail, dict):
            error_code = exc.detail.get("code", "HTTP_ERROR")
            message = exc.detail.get("message", str(exc.detail))
            for k, v in exc.detail.items():
                if k not in ("code", "message"):
                    details[k] = v

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": error_code,
                    "message": message,
                    "details": details,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                "detail": detail_obj,
            },
        )

    @app.exception_handler(Exception)
    async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server exception on %s: %s", request.url.path, exc)
        return create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred. The incident has been logged.",
            details={"path": request.url.path},
        )
