# PS-05 Digital Evidence Authenticity & Integrity Verification Platform

> **System Classification:** High-Integrity Digital Forensics & Chain-of-Custody Verification  
> **Compliance Standards:** ISO/IEC 27037, ISO/IEC 27042, NIST SP 800-86, Federal Rules of Evidence (FRE 901/902)  
> **Status:** Phase 2 Domain Entities & Audit Immutability Verified (Ready for Phase 3 Ingestion Engine)

---

### Architectural Overview

The **PS-05 Platform** is an enterprise-grade digital forensics platform engineered to verify the authenticity and integrity of digital media evidence (image, audio, and video).

```
digital-forensics/
├── apps/
│   └── web/                   # Next.js 14, TypeScript & Tailwind CSS Investigative Console
├── services/
│   └── api/                   # FastAPI Modular Monolith & Shared Worker Backend
│       ├── app/main.py        # HTTP API entry point
│       └── app/worker.py      # Background worker process entry point
├── storage/                   # Private Local Evidence Vaults
│   ├── originals/             # Immutable bitstream-intact originals (POSIX 0400 target)
│   ├── artifacts/             # Derivative forensic outputs (ELA heatmaps, spectrograms, frames)
│   ├── reports/               # Courtroom PDF examination reports
│   └── tmp/                   # Ephemeral upload staging and scratch area
├── docker-compose.yml         # Container orchestration (API, Worker, Web, Postgres 16, Redis 7)
├── Makefile                   # Standard developer lifecycle workflow
└── run.ps1                    # Native Windows PowerShell automation helper
```

---

### Quick Start & Development

#### 1. Setup Environment
```bash
# Using Makefile
make setup

# Or on Windows using PowerShell:
.\run.ps1 setup
```

#### 2. Configure secrets before starting

Copy the template and replace both placeholders with unique values. Do not commit your local `.env` file.

```bash
# Linux/macOS/Git Bash
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

Generate a strong API signing key with Python:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Use a generated random value for `SECRET_KEY`. Generate a second value with the same command for `POSTGRES_PASSWORD`, then copy that exact database password into `DATABASE_URL`. `token_hex(32)` produces URL-safe hexadecimal characters, avoiding connection-string parsing errors. Do not reuse the API signing key as the database password. The Compose configuration refuses to start without the required values. PostgreSQL and Redis are private to the Compose network; the web and API ports bind to localhost for local development.

#### 3. Run with Docker Compose
```bash
# Launch PostgreSQL, Redis, FastAPI Backend, Worker, and Next.js Frontend:
docker compose up -d

# Check service health:
docker compose ps
```

#### 4. Run Locally (Direct Development Mode)

**Backend API:**
```bash
cd services/api
..\..\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Background Worker:**
```bash
cd services/api
..\..\.venv\Scripts\python -m app.worker
```

**Frontend Console:**
```bash
cd apps/web
npm run dev
```

---

### Health & Readiness Endpoints

| Endpoint | Method | Purpose | Response |
| :--- | :--- | :--- | :--- |
| `/health` or `/api/v1/health` | `GET` | Liveness probe verifying the API process is alive | `{"status": "OPERATIONAL", "version": "0.1.0"}` |
| `/ready` or `/api/v1/ready` | `GET` | Readiness probe testing PostgreSQL, Redis, and Storage directories | `{"status": "READY", "subsystems": {...}}` |

---

### Testing, Linting & Type Checking

```bash
# Execute Pytest test suite:
cd services/api
..\..\.venv\Scripts\python -m pytest -v

# Run Python linter:
cd services/api
..\..\.venv\Scripts\ruff check .

# Run strict Python type check:
cd services/api
..\..\.venv\Scripts\mypy app tests

# Run Frontend TypeScript check:
cd apps/web
npm run typecheck

# Run Frontend linter:
cd apps/web
npm run lint
```

---

### Phase 1 Architectural Guarantees

1. **Strict Layer Separation:** API routers, configuration, persistence, storage management, and exception handlers are segregated.
2. **Path Traversal Security:** `StorageManager.secure_resolve_path()` prevents directory traversal attempts (`../../`) out of the vault root.
3. **Structured Error Handling:** Standardized error JSON responses with RFC-7807 compliance, domain error codes, and audit timestamps.
4. **Decoupled Worker Architecture:** `app/worker.py` runs independently from the HTTP server while sharing configuration, storage, and database access.
