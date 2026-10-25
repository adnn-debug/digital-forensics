# PS-05 Digital Evidence Authenticity & Integrity Verification Platform

> **System Classification:** High-Integrity Digital Forensics & Chain-of-Custody Verification Platform  
> **Challenge:** Bihar Cyber Hackathon 2026 (Problem Statement PS-05)  
> **Compliance Standards:** ISO/IEC 27037, ISO/IEC 27042, NIST SP 800-86, Federal Rules of Evidence (FRE 901/902)  
> **Status:** Phases 1–8 Fully Implemented & Verified (21/21 Tasks Verified, 109 Pytest Tests Passing, Next.js Build Clean)

---

### Architectural Overview

The **PS-05 Platform** is an enterprise-grade digital forensics platform engineered to verify the authenticity and integrity of digital media evidence (image, audio, and video).

```
digital-forensics/
├── apps/
│   └── web/                   # Next.js 14, TypeScript & Tailwind CSS Investigative Console (App Router)
├── services/
│   └── api/                   # FastAPI Modular Monolith & Decoupled Background Worker
│       ├── app/main.py        # HTTP API entry point (FastAPI + ASGI)
│       ├── app/worker.py      # Background worker process entry point (Redis Queue / RQ)
│       ├── app/forensics/     # Media analysis engines (Pillow ELA, OpenCV, SciPy STFT, ExifTool, FFprobe)
│       └── app/reports/       # ReportLab Platypus Courtroom PDF Engine with QR & Hash Seals
├── storage/                   # Private Local Evidence Vaults (git-ignored)
│   ├── originals/             # Bitstream originals (chmod 0400 / stat.S_IREAD read-only locked)
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

#### 2. Run with Docker Compose
```bash
# Launch PostgreSQL 16, Redis 7, FastAPI Backend, RQ Worker, and Next.js Frontend:
docker compose up -d

# Check service health:
docker compose ps
```

#### 3. Run Locally (Direct Development Mode)

**Backend API:**
```bash
cd services/api
..\..\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Background Worker (Redis Queue / RQ):**
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
# Execute Pytest test suite (109 passing unit and integration tests):
cd services/api
..\..\.venv\Scripts\python -m pytest -v

# Run strict Python type check (100 files clean):
cd services/api
..\..\.venv\Scripts\mypy --config-file mypy.ini app tests

# Run Python linter:
cd services/api
..\..\.venv\Scripts\ruff check . --config pyproject.toml

# Run Frontend TypeScript check:
cd apps/web
npm run typecheck

# Run Frontend linter:
cd apps/web
npm run lint

# Build production Frontend:
cd apps/web
npm run build
```

---

### Core Forensic & Architectural Guarantees (Phases 1–8)

1. **Strict Layer Separation:** API routers, persistence, storage management, analysis engines, and exception handlers are segregated. Responses are strictly serialized through Pydantic DTOs.
2. **Read-Only Evidence Vaults:** Ingested evidence bitstreams are locked read-only (`chmod 0400` / `stat.S_IREAD`) in `storage/originals/`. Derived artifacts and reports reside in separate directories.
3. **Database-Level Anti-Tamper Enforcement:** SQL triggers on `audit_events` and `evidence_items.primary_hash_sha256` reject any SQL `UPDATE` or `DELETE` attempt at the database engine level.
4. **Streaming Multi-Hasher:** Concurrently calculates SHA-256 (forensic baseline), SHA-1, and MD5 during network upload streaming with bounded RAM consumption.
5. **Durable Task Queue:** Compute-heavy forensic analyses are decoupled from the HTTP cycle via Redis Queue (RQ) and backed by PostgreSQL authoritative state mirroring, idempotency guards, and automatic worker crash recovery.
6. **Multi-Modal Forensic Heuristics:** Sandboxed ExifTool and FFprobe metadata extraction, Pillow/NumPy Error Level Analysis (ELA), OpenCV video scene cuts and keyframe slicing, and SciPy audio STFT spectrogram analysis.
7. **Courtroom PDF Examination Reports:** ReportLab Platypus layout engine generating deterministic, vector-sealed PDF examination reports complete with dynamic QR verification codes and chain-of-custody audit logs.
