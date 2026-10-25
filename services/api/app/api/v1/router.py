"""API v1 master router aggregator."""

from fastapi import APIRouter

from app.api.v1 import analysis, auth, cases, evidence, health, reports

api_v1_router = APIRouter()

# Core diagnostics
api_v1_router.include_router(health.router)

# Authentication
api_v1_router.include_router(auth.router)

# Case management
api_v1_router.include_router(cases.router)

# Evidence intake and verification
api_v1_router.include_router(evidence.router)

# Forensic analysis jobs and execution history
api_v1_router.include_router(analysis.router)

# Courtroom examination reports
api_v1_router.include_router(reports.router)

