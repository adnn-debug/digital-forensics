# Deployment Readiness — PS-05 Digital Evidence Platform

## Current status

**Status: prototype / pre-deployment.** The repository contains the main application paths for evidence intake, hashing, metadata extraction, image/audio/video analysis, background jobs, case access, and PDF reports. The current hardening branch also adds safer local Compose defaults and token-based report integrity verification.

This document deliberately separates **implemented in code** from **verified in a running deployment**. At the time of writing, the current branch has not completed a fresh CI pass or an end-to-end deployment test. Do not represent the server as production-ready or certified for law-enforcement evidence handling yet.

## Deployment blockers

### 1. Establish a trustworthy test result

- Enable/repair GitHub Actions so jobs actually execute. Current run records show failed workflow runs with zero jobs, which is not a test result.
- Run backend Ruff and pytest, frontend ESLint and TypeScript checks, and a production Next.js build.
- Run Alembic migrations against a disposable PostgreSQL instance, not only SQLite.
- Run the full stack and verify login/logout revocation, role/case authorization, evidence upload, hash verification, worker processing/retry, report generation/download, and QR verification.
- Fix every reproducible failure and rerun the full suite before merging.

### 2. Choose a production storage topology

The current LocalFilesystemStorageAdapter stores originals, derived artifacts, and reports on a local filesystem. Docker Compose shares the storage directory between API and worker, which is appropriate for local development.

For a hosted deployment, **the API and worker must see the same durable storage namespace**. A single persistent disk attached to only one of two separately deployed services is not sufficient. Prefer an S3-compatible private object store (with versioning/object lock where available) and implement/test a production storage adapter, or deliberately choose a single-host deployment with a persistent disk mounted to both API and worker. Do not deploy with ephemeral container storage for evidence.

### 3. Provision and secure production services

- HTTPS domain/reverse proxy for the web app and API.
- Managed PostgreSQL with automated backups, restore testing, least-privilege credentials, and migration procedure.
- Private Redis with authentication/TLS appropriate to the provider; it is required for login throttling, token revocation, and the analysis queue.
- Unique production SECRET_KEY; DEBUG=false; ENVIRONMENT=production; correct HTTPS FRONTEND_URL; secret values stored in the host's secret manager, never committed.
- Durable evidence/artifact/report storage, access controls, retention policy, and tested recovery.
- Non-root containers, resource limits, upload/request limits, rate limiting, dependency scanning, monitoring/alerts, and operational logs without sensitive evidence data.

### 4. Verify operational and forensic behavior

- Seed the first administrator securely; do not add a public default admin credential.
- Confirm role-based access for every case/evidence/report endpoint, including download and verification paths.
- Test malicious uploads, large files, interrupted uploads, duplicate evidence, path traversal, worker crash recovery, and tampered stored files.
- Verify that audit events form the intended chain, that concurrency cannot silently fork it, and that chain verification detects altered records.
- Back up and restore PostgreSQL plus evidence storage together, and verify that hashes still match after restoration.
- Treat ELA, waveform, spectrogram, and video scene-cut outputs as examiner-supporting indicators, not proof of authenticity by themselves. Obtain independent forensic/legal review before making admissibility or compliance claims.

## Local smoke-test commands

Run from the repository root after configuring .env:

    docker compose config --quiet
    docker compose up --build -d
    docker compose ps
    Invoke-RestMethod http://localhost:8000/api/v1/health
    Invoke-RestMethod http://localhost:8000/api/v1/ready

Backend checks:

    cd services/api
    python -m ruff check .
    python -m pytest -v
    python -m mypy app tests

Frontend checks:

    cd apps/web
    npm ci
    npm run typecheck
    npx eslint .
    npm run build

These are the commands to run; they are **not evidence that the checks have already passed**.

## Release gate

Do not call the objective fully achieved until all of the following are true:

1. CI is green on the exact commit intended for release.
2. PostgreSQL migration and restore procedures are tested.
3. A real deployment is live over HTTPS with persistent shared evidence storage.
4. An end-to-end demo succeeds on the deployed URL using non-sensitive sample evidence.
5. The deployed health/readiness probes pass and logs show the worker processing jobs.
6. QR verification succeeds for an intact report and fails after a controlled tamper test.
7. The demo has a clear limitations statement and does not claim legal admissibility or formal standards compliance without independent validation.
