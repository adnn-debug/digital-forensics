"""FastAPI main application entrypoint for PS-05 Digital Evidence Platform."""

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.deps import get_storage
from app.api.v1.health import health_check, readiness_check
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.db.session import close_db_engine

logger = logging.getLogger("ps05.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup initialization and graceful shutdown."""
    settings = get_settings()

    # 1. Initialize structured logging
    setup_logging(
        log_level=settings.LOG_LEVEL,
        json_format=(settings.ENVIRONMENT in ("production", "staging")),
    )
    logger.info("Starting %s in [%s] mode...", settings.PROJECT_NAME, settings.ENVIRONMENT)

    # 2. Verify and initialize private storage vaults
    storage = get_storage()
    storage.initialize_directories()
    logger.info("Storage directories initialized at: %s", settings.STORAGE_BASE_PATH)

    yield

    # 3. Graceful shutdown operations
    logger.info("Shutting down %s...", settings.PROJECT_NAME)
    await close_db_engine()
    logger.info("Database connection pools closed cleanly.")


def create_app() -> FastAPI:
    """Application factory for FastAPI modular monolith."""
    settings = get_settings()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=(
            "High-integrity forensic evidence verification, hashing, analysis, "
            "and courtroom reporting platform."
        ),
        version="0.1.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # Security & CORS Middleware
    frontend_origins = [
        settings.FRONTEND_URL,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    if "localhost" in settings.FRONTEND_URL:
        frontend_origins.append(settings.FRONTEND_URL.replace("localhost", "127.0.0.1"))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(dict.fromkeys(frontend_origins)),
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Request Timing and Security Headers Middleware
    @app.middleware("http")
    async def add_security_and_timing_headers(request: Request, call_next: Any) -> Response:
        start_time = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            logger.exception("Unhandled error processing %s %s: %s", request.method, request.url.path, exc)
            origin = request.headers.get("origin") or "*"
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "An unexpected server error occurred. The incident has been logged.",
                        "details": {"path": request.url.path},
                    }
                },
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Allow-Methods": "*",
                },
            )

        process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Forensic Audit & Security Headers
        response.headers["X-Process-Time-MS"] = str(process_time_ms)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # Centralized Exception Handling
    register_exception_handlers(app)

    # Mount API v1 Routes
    app.include_router(api_v1_router, prefix=settings.API_V1_STR)

    # Root Level Health Check Aliases (useful for standard Kubernetes / Docker health probes)
    app.add_api_route("/health", health_check, methods=["GET"], tags=["Root Health"])
    app.add_api_route("/ready", readiness_check, methods=["GET"], tags=["Root Readiness"])

    return app


app = create_app()
