# PS-05 Digital Evidence Platform — Project Context

> **System Classification:** High-Integrity Digital Forensics & Chain-of-Custody Verification  
> **Compliance Standards:** ISO/IEC 27037, ISO/IEC 27042, NIST SP 800-86, Federal Rules of Evidence (FRE 901/902)  
> **Last Verified Date:** 2026-10-23  

---

## 1. Project Purpose & Core Capabilities

The **PS-05 Platform** is an enterprise digital forensics solution built to ingest, verify, analyze, and report on digital media evidence (images, audio, and video) with courtroom-admissible integrity guarantees.

### Key Capabilities
1. **Cryptographic Baseline Hashing:** Immediate SHA-256 baseline calculation (with concurrent SHA-1 and MD5 legacy digests) at the exact stream ingestion boundary.
2. **Immutable Chain of Custody:** Tamper-evident, append-only audit event logging cryptographically chained and protected by database triggers.
3. **Forensic Soundness:** Automated execution of standard forensic heuristics:
   - EXIF/container metadata extraction via ExifTool and FFprobe.
   - JPEG Error Level Analysis (ELA) for image compression disparity detection.
   - Video temporal analysis with scene change and keyframe slicing (OpenCV).
   - Audio Short-Time Fourier Transform (STFT) spectrogram and waveform analysis (librosa/SciPy).
4. **Courtroom Admissibility:** Cryptographically verifiable PDF examination reports containing embedded hash seals, audit extracts, and analysis summaries.

---

## 2. Technology Stack & Architectural Style

### Architectural Pattern
- **Modular Monolith + Decoupled Worker Fleet:**
  - Fast HTTP API (FastAPI) handles request routing, validation, and session coordination.
  - Decoupled background workers (Celery + Redis) handle CPU- and memory-intensive forensic computations.
  - Shared persistence layer (PostgreSQL 16) and private local/cloud evidence vault.

### Core Technologies
| Subsystem | Technology | Version / Configuration |
| :--- | :--- | :--- |
| **Backend Framework** | Python / FastAPI | Python 3.11+, ASGI, Starlette |
| **Data Validation** | Pydantic / Pydantic Settings | Pydantic v2 |
| **Database & ORM** | PostgreSQL 16 (Target) / SQLAlchemy | SQLAlchemy 2.0 (Async), `asyncpg`, `aiosqlite` for tests |
| **Migrations** | Alembic | Async migration environment |
| **Message Broker** | Redis | Redis 7.x (Target) / `fakeredis` for testing |
| **Asynchronous Worker** | Celery | Configured for decoupled process execution |
| **External CLI Tooling** | ExifTool, FFmpeg / FFprobe | Sandboxed non-root subprocesses |
| **Python Scientific Tools** | Pillow, OpenCV, NumPy, SciPy, librosa | Native in-process workers |
| **Report Generation** | ReportLab | Platypus document layout engine |
| **Frontend Console** | Next.js 14, React 18, TypeScript, Tailwind CSS | App Router, Typed API client |

---

## 3. Repository Structure & Key Modules

```
digital-forensics/
├── .env.example                       # Reference environment variables
├── .env                               # Local development environment configuration
├── docker-compose.yml                 # Multi-container orchestration (API, Worker, Web, DB, Redis)
├── Makefile                           # Developer workflow targets
├── run.ps1                            # Windows PowerShell lifecycle helper
├── README.md                          # Platform overview and quickstart
├── AI_WORKLOG.md                      # Chronological development and test ledger
├── PROJECT_CONTEXT.md                 # System state, conventions, and context (this file)
├── TASK_TRACKER.md                    # Multi-phase milestone and task status register
├── DECISIONS.md                       # Architecture Decision Records log
├── docs/                              # Architecture blueprints & threat models
│   ├── ADR.md                         # Architecture Decision Records (canonical)
│   ├── ARCHITECTURE.md                # System architectural blueprint
│   ├── DATA_FLOW.md                   # Ingestion and processing data flow specs
│   ├── FORENSIC_LIMITATIONS.md        # Technical heuristics and legal boundaries
│   ├── PLAN.md                        # Master implementation roadmap (Phases 1-8)
│   ├── REPO_TREE.md                   # File tree specification
│   └── SECURITY_THREAT_MODEL.md       # STRIDE threat model & mitigations
├── apps/
│   └── web/                           # Next.js 14 Frontend Investigative Console
│       ├── src/app/                   # App Router pages and layouts
│       ├── src/components/            # UI components and system monitors
│       └── src/lib/api.ts             # Typed API client for health/readiness
├── services/
│   └── api/                           # FastAPI Backend Modular Monolith
│       ├── alembic/                   # Database schema migrations
│       │   ├── env.py                 # Async Alembic execution environment
│       │   └── versions/              # Migration scripts (0001_initial_schema.py)
│       ├── app/
│       │   ├── api/                   # HTTP Routers (v1) and dependencies
│       │   ├── core/                  # Configuration (config.py) and exceptions
│       │   ├── db/                    # Database session, base model, triggers
│       │   │   ├── models/            # SQLAlchemy 2.0 ORM domain entities
│       │   │   ├── triggers.py        # Database anti-tamper triggers
│       │   │   └── session.py         # Async connection pool & connectivity checks
│       │   ├── storage/               # Storage manager & path security
│       │   ├── main.py                # FastAPI HTTP application entrypoint
│       │   └── worker.py              # Background worker entrypoint
│       └── tests/                     # Pytest suite
│           ├── conftest.py            # Test fixtures (isolated storage, in-memory DB)
│           ├── integration/           # Anti-tamper & model relationship tests
│           └── test_*.py              # Config, exceptions, health, and storage tests
└── storage/                           # Private Local Evidence Vaults (git-ignored)
    ├── originals/                     # Bitstream originals (chmod 0400 target)
    ├── artifacts/                     # Derived outputs (heatmaps, plots, frames)
    ├── reports/                       # Courtroom PDF examination reports
    └── tmp/                           # Ephemeral upload staging and scratch area
```

---

## 4. Current Implementation Status

| Milestone | Scope | Verified Status |
| :--- | :--- | :--- |
| **Phase 1** | Scaffolding, Docker Compose & Core Infrastructure | **Verified** (12 unit tests passing, health/readiness endpoints active) |
| **Phase 2** | Domain Modeling, DB Migrations & Immutability Triggers | **Verified** (Models created, Alembic 0001 schema created, 4 integration tests passing) |
| **Phase 3** | Storage Abstraction, Multi-Hasher & Evidence Ingestion | **Planned** (Next active task) |
| **Phase 4** | Durable Celery Worker & Metadata Extraction | **Planned** |
| **Phase 5** | Deep Forensic Analysis Engines (ELA, Video, Audio) | **Planned** |
| **Phase 6** | Courtroom PDF Report Engine (ReportLab) | **Planned** |
| **Phase 7** | Next.js Forensic Dashboard & Media Visualizers | **Planned** |
| **Phase 8** | System Hardening & End-to-End Acceptance | **Planned** |

---

## 5. Security Invariants & Engineering Constraints

1. **Database-Level Immutability (Anti-Tamper):**
   - The `audit_events` table is physically append-only. Any SQL `UPDATE` or `DELETE` is blocked at the database engine level by database triggers raising `CRITICAL SECURITY VIOLATION`.
   - The `evidence_items.primary_hash_sha256` column is permanently immutable once inserted.
2. **Path Traversal Protection:**
   - Any path resolution must pass through `StorageManager.secure_resolve_path()` to ensure storage operations cannot escape the configured vault root directory.
3. **Layer Separation:**
   - API routers must not execute database queries directly or perform disk file I/O. All operations must flow through domain services.
   - ORM models must not be returned directly in API route handlers; responses must be serialized through explicit Pydantic DTOs.
4. **Streaming Hash Calculation:**
   - Hashes must be computed on the fly as chunks arrive in the stream to prevent buffering large files into memory.
5. **No Secrets in Repository:**
   - Keys, credentials, and passwords must never be hardcoded and must be loaded strictly from environment variables.

---

## 6. Known Technical Limitations & Environment Notes

- **Host Environment:** Windows local environment without native Docker engine in PATH. Unit and integration tests run cleanly using Python's `aiosqlite` with `StaticPool` and in-memory `fakeredis`. Full multi-container verification requires Docker.
- **Subprocess Dependencies:** External binaries `exiftool` and `ffmpeg` are required for Phase 4 worker execution; they are installed in the container image and must be installed on the host if running tests directly outside Docker.
