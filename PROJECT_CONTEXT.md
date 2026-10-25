# PS-05 Digital Evidence Platform — Project Context

> **System Classification:** High-Integrity Digital Forensics & Chain-of-Custody Verification Platform  
> **Challenge:** Bihar Cyber Hackathon 2026 (Problem Statement PS-05)  
> **Compliance Standards:** ISO/IEC 27037 (Digital Evidence Handling), ISO/IEC 27042, NIST SP 800-86, Federal Rules of Evidence (FRE 901/902)  
> **Last Verified Date:** 2026-10-25  
> **Verification Status:** Phases 1–8 Fully Implemented & Verified (21/21 Tasks Verified, 109 Pytest Tests Passing, Next.js Build Passing)

---

## 1. Project Purpose & Scope

The **PS-05 Platform** is an enterprise-grade digital forensics application designed to ingest, verify, analyze, and report on digital media evidence (images, audio, and video) with courtroom-admissible integrity guarantees.

### Core Capabilities
1. **Cryptographic Stream Hashing:** Concurrent computation of SHA-256 (forensic baseline), SHA-1, and MD5 (legacy cross-referencing) during initial upload streaming without buffering entire files into memory.
2. **Immutable Chain of Custody:** Cryptographically chained audit event logs enforced by database-level triggers blocking SQL `UPDATE` and `DELETE` operations.
3. **Automated Multi-Modal Forensics:**
   - **Metadata Extraction:** Sandboxed ExifTool and FFprobe subprocess wrappers extracting EXIF metadata, camera MakerNotes, audio/video stream structures, codecs, and container formats.
   - **Image Forensics:** JPEG Error Level Analysis (ELA) using Pillow and NumPy to detect compression rate disparities and generate visualization heatmaps.
   - **Video Forensics:** OpenCV temporal scene-cut analysis, keyframe extraction, and difference hashing (dHash) for visual integrity tracking.
   - **Audio Forensics:** SciPy Short-Time Fourier Transform (STFT) spectral analysis, Matplotlib spectrogram and waveform generation, and sample clipping detection.
4. **Courtroom-Ready Reporting:** Deterministic PDF examination reports compiled via ReportLab Platypus, incorporating vector hash seals, dynamic QR verification codes, and chain-of-custody audit logs.
5. **Investigative Web Console:** Next.js 14 console featuring case/evidence management, chunked upload, interactive dual-slider ELA heatmap comparison, audio waveform players, video keyframe carousels, and PDF report downloads.

---

## 2. Verified Technology Stack

### Backend Services (`services/api`)
- **Runtime:** Python 3.11+
- **API Framework:** FastAPI (`>=0.110.0,<0.116.0`), Uvicorn (`>=0.28.0,<0.33.0`), Starlette
- **Data Validation & Settings:** Pydantic v2 (`>=2.6.4,<3.0.0`), Pydantic Settings (`>=2.2.1,<3.0.0`)
- **Database Engine & ORM:** SQLAlchemy 2.0 (`>=2.0.28,<2.1.0`) with async session factory; `asyncpg` (`>=0.29.0`) for PostgreSQL 16; `aiosqlite` (`>=0.20.0`) for isolated in-memory test suites
- **Schema Migrations:** Alembic (`>=1.13.1,<1.14.0`)
- **Asynchronous Task Queue:** **Redis Queue (RQ `~=2.0.0`)** via `redis` (`>=5.0.3,<5.3.0`) and `fakeredis` (`>=2.21.3`). *Note: While early architectural drafts evaluated Celery, RQ was selected and implemented for Phase 4 for its lightweight footprint, reliable Windows local worker compatibility (`SimpleWorker`), and direct PostgreSQL state synchronization.*
- **Forensic Computation & DSP:** Pillow (`>=10.0.0`), OpenCV Headless (`>=4.8.0`), NumPy (`>=1.26.0`), SciPy (`>=1.12.0`), Matplotlib (`>=3.8.0`)
- **PDF Generation & Cryptographic Verification:** ReportLab (`>=4.0.0`), PyPDF (`>=4.0.0`), QRCode (`>=7.4.0`)
- **Authentication & Cryptography:** `python-jose[cryptography]`, `passlib[bcrypt]`

### Frontend Investigative Console (`apps/web`)
- **Framework:** Next.js 14 (`14.2.24`), React 18 (`18.3.1`), TypeScript (`5.6.3`)
- **Architecture:** Next.js App Router with server-rendered pages and client-side interactive visualizers
- **Styling & UI:** Tailwind CSS (`3.4.14`), Lucide Icons (`0.453.0`), `clsx`, `tailwind-merge`

### Infrastructure & Storage
- **Container Orchestration:** `docker-compose.yml` defining PostgreSQL 16 Alpine, Redis 7 Alpine, API monolith, decoupled background worker, and Next.js frontend
- **Storage Subsystem:** Local filesystem storage provider partitioned into four isolated vaults:
  - `storage/originals/`: Read-only locked evidence bitstreams (`chmod 0400` POSIX / `stat.S_IREAD` Windows)
  - `storage/artifacts/`: Derived forensic outputs (ELA heatmaps, spectrograms, extracted frames)
  - `storage/reports/`: Compiled courtroom PDF examination reports
  - `storage/tmp/`: Staging area for chunked uploads and atomic two-phase transactions

---

## 3. Verified Repository Structure

```
digital-forensics/
├── .env                               # Local configuration file (git-ignored)
├── .env.example                       # Reference environment variables
├── docker-compose.yml                 # Multi-container orchestration (DB, Redis, API, Worker, Web)
├── Makefile                           # Development lifecycle shortcuts
├── run.ps1                            # Windows PowerShell lifecycle helper
├── AGENTS.md                          # Permanent operating instructions for AI coding agents
├── HANDOFF.md                         # Primary status and handoff document for new AI sessions
├── CURRENT_TASK.md                    # Active task checkpoint (empty when no task is active)
├── AI_WORKLOG.md                      # Chronological development and test ledger
├── PROJECT_CONTEXT.md                 # Stable system architecture and conventions (this file)
├── TASK_TRACKER.md                    # Implementation status register (Prompts 1–8 verified)
├── DECISIONS.md                       # Architecture Decision Records (ADR-001 through ADR-009)
├── README.md                          # Project overview and quickstart
├── docs/                              # Architecture blueprints and threat models
│   ├── ADR.md                         # Architecture Decision Records
│   ├── ARCHITECTURE.md                # System architectural blueprint
│   ├── DATA_FLOW.md                   # Ingestion and processing data flow specs
│   ├── DURABLE_BACKGROUND_JOBS.md     # RQ worker and PostgreSQL state mirroring specification
│   ├── FORENSIC_LIMITATIONS.md        # Technical heuristics and legal boundaries
│   ├── PLAN.md                        # Master implementation roadmap (Phases 1–8)
│   ├── REPO_TREE.md                   # File tree specification
│   └── SECURITY_THREAT_MODEL.md       # STRIDE threat model & mitigations
├── apps/
│   └── web/                           # Next.js 14 Investigative Console
│       ├── package.json               # Frontend dependencies & build scripts
│       └── src/
│           ├── app/                   # App Router pages (9 verified routes)
│           │   ├── page.tsx           # Operational subsystems dashboard
│           │   ├── login/             # Examiner login view
│           │   ├── cases/             # Case register and detail views
│           │   ├── upload/            # Evidence intake wizard
│           │   ├── analysis/          # Cross-case analysis jobs register
│           │   ├── reports/           # Courtroom PDF report generator
│           │   └── cases/[caseId]/evidence/[evidenceId]/
│           │       ├── page.tsx       # Evidence examination overview
│           │       ├── image-analysis # Interactive ELA heatmap comparison slider
│           │       ├── audio-analysis # Synchronized STFT spectrogram & waveform viewer
│           │       └── video-analysis # Video keyframe carousel & temporal cut player
│           ├── components/            # Reusable UI widgets and navigation
│           └── lib/api.ts             # Typed REST API client
├── services/
│   └── api/                           # FastAPI Backend Modular Monolith
│       ├── Dockerfile                 # Multi-stage container with ExifTool & FFmpeg
│       ├── requirements.txt           # Python backend dependencies
│       ├── pyproject.toml             # Ruff, Pytest, and Black configurations
│       ├── mypy.ini                   # Mypy type-checking configuration
│       ├── alembic/                   # Database migrations (0001_initial_schema.py)
│       ├── app/
│       │   ├── main.py                # FastAPI HTTP entrypoint
│       │   ├── worker.py              # Dedicated background worker entrypoint
│       │   ├── api/                   # HTTP endpoints and routers
│       │   │   ├── deps.py            # Dependency injection (Auth, DB, Storage)
│       │   │   └── v1/                # Versioned routers (health, auth, cases, evidence, analysis, reports)
│       │   ├── core/                  # Configuration, logging, security, and exceptions
│       │   ├── db/                    # SQLAlchemy engine, session, and models
│       │   │   ├── models/            # Domain entities (User, Case, EvidenceItem, etc.)
│       │   │   ├── session.py         # Async connection pool & connectivity checks
│       │   │   └── triggers.py        # Database anti-tamper trigger definitions
│       │   ├── forensics/             # Media analysis engines and subprocess adapters
│       │   │   ├── base.py            # Base adapter interfaces and findings DTOs
│       │   │   ├── exif_adapter.py    # Sandboxed ExifTool wrapper
│       │   │   ├── ffprobe_adapter.py # Sandboxed FFprobe stream wrapper
│       │   │   ├── image_engine.py    # Pillow/NumPy Error Level Analysis engine
│       │   │   ├── video_engine.py    # OpenCV keyframe and scene detector
│       │   │   ├── audio_engine.py    # SciPy/Matplotlib STFT and waveform analyzer
│       │   │   └── metadata_service.py# Orchestrator for metadata ingestion
│       │   ├── queue/                 # Redis Queue (RQ) worker integration
│       │   │   ├── connection.py      # Redis sync/async connection management
│       │   │   ├── queue.py           # RQ queue definitions and queue statistics
│       │   │   ├── service.py         # Job orchestration and PostgreSQL state mirroring
│       │   │   └── tasks.py           # Background task execution handlers
│       │   ├── reports/               # Courtroom PDF report generator
│       │   │   ├── builder.py         # Platypus layout engine
│       │   │   ├── canvas.py          # Numbered canvas with running header/footer
│       │   │   └── seals.py           # Cryptographic QR and hash seal generators
│       │   ├── repositories/          # Data access layer (CRUD for all 9 entities)
│       │   ├── schemas/               # Pydantic DTOs and API contracts
│       │   ├── services/              # Domain services (EvidenceService, VerificationService, etc.)
│       │   └── storage/               # Storage manager, LocalFilesystemAdapter, MultiHasher
│       └── tests/                     # Test suite (109 passing tests)
│           ├── conftest.py            # In-memory DB, storage fixtures, mock tokens
│           ├── integration/           # Multi-component and anti-tamper tests
│           └── unit/                  # Isolated adapter and algorithm tests
└── storage/                           # Private Local Evidence Vaults (git-ignored)
    ├── originals/                     # Bitstream originals (chmod 0400 locked)
    ├── artifacts/                     # Derived outputs (ELA heatmaps, plots, frames)
    ├── reports/                       # Courtroom PDF reports
    └── tmp/                           # Ephemeral upload staging and scratch area
```

---

## 4. Database & Storage Architecture

### Database Responsibilities
- **Single Source of Truth:** PostgreSQL 16 stores all domain models (`users`, `cases`, `evidence_items`, `hash_verifications`, `metadata_extracts`, `forensic_analyses`, `analysis_artifacts`, `findings`, `audit_events`, `reports`).
- **In-Memory Testing Support:** Fully functional with `aiosqlite` in memory with `PRAGMA foreign_keys=ON` and `StaticPool`.
- **Database-Level Anti-Tamper Triggers (`app/db/triggers.py`):**
  - `audit_events`: Any SQL `UPDATE` or `DELETE` is permanently blocked by database triggers (PL/pgSQL on PostgreSQL, SQL triggers on SQLite) raising `CRITICAL SECURITY VIOLATION: audit_events is append-only`.
  - `evidence_items.primary_hash_sha256`: Any SQL `UPDATE` attempting to alter the baseline SHA-256 hash is rejected by trigger with `CRITICAL SECURITY VIOLATION: primary_hash_sha256 is permanently immutable`.

### Storage Responsibilities & Two-Phase Ingestion
- Ingestion operates via `StagedStorageTransaction`:
  1. Incoming byte chunks are streamed to an ephemeral staging location in `storage/tmp/`.
  2. Concurrent multi-hasher computes SHA-256, SHA-1, and MD5 during streaming.
  3. If database transaction succeeds: File is atomically moved from `tmp/` into `storage/originals/` and permissions are locked to read-only (`0400` POSIX / `stat.S_IREAD` Windows).
  4. If database transaction fails or upload is aborted: Staging file in `tmp/` is unlinked during rollback, preventing phantom storage records or orphaned files.
- Periodic maintenance utilities (`cleanup_temporary_files` and `reconcile_orphaned_files`) sweep orphaned temporary files and alert on missing disk files.

---

## 5. Security & Provenance Conventions

1. **Authentication & RBAC:**
   - Stateless JWT Bearer tokens signed with HMAC-SHA256 (`HS256`).
   - Role-Based Access Control enforcing `ADMIN`, `EXAMINER`, and `INVESTIGATOR` permissions.
   - Examiners can only access cases they own; Admins possess global case access.
2. **Path Traversal Mitigation:**
   - All filesystem operations route through `StorageManager.secure_resolve_path()`, which canonicalizes paths and verifies they reside strictly inside the configured vault root directory.
3. **Subprocess Isolation:**
   - External CLI tools (ExifTool, FFprobe) are executed with explicit argument lists (never `shell=True`), strict execution timeouts (default 30s), bounded output read buffers (10MB maximum), and path traversal sanitation.
4. **Cryptographic Re-Verification:**
   - Independent verification endpoint (`POST /api/v1/evidence/{id}/verify-hash`) re-reads stored original bytes in bounded 64KB chunks to recalculate SHA-256 against the immutable database baseline.
   - Bit-flips immediately fail verification and trigger an immutable `TAMPER_DETECTED` audit alert.

---

## 6. Background Job & Worker Fleet Architecture

1. **Redis Transport & PostgreSQL Authority:**
   - Tasks are dispatched to Redis Queue (`forensic_analysis` queue).
   - Authoritative job lifecycle state is mirrored in the PostgreSQL `forensic_analyses` table (`QUEUED` -> `PROCESSING` -> `COMPLETED` / `FAILED` / `SKIPPED`).
2. **Idempotency Protection:**
   - Client-provided `idempotency_key` (via body or `X-Idempotency-Key` header) deduplicates requests.
   - In-flight duplicate guard prevents spawning concurrent duplicate worker tasks for the same evidence and analysis type.
3. **Retry Deduplication:**
   - On job retry, `clear_findings_for_analysis()` atomically purges any partial findings from prior failed attempts before staging new results.
4. **Crash Recovery:**
   - `ForensicWorker` automatically runs crash recovery on startup.
   - Watchdog sweeps scan for orphaned `PROCESSING` jobs whose heartbeats expired (`> 60s`), re-enqueuing them if retries remain or marking them `FAILED`.
   - On Windows, worker runs `SimpleWorker` to circumvent OS fork limitations; Linux production containers use standard multi-process `Worker`.

---

## 7. Courtroom PDF Report Generation

- Built with ReportLab Platypus (`app/reports/builder.py`).
- Deterministic page budget calculations with `NumberedCanvas` (`app/reports/canvas.py`), outputting running headers, confidential classification marks, page counts ("Page X of Y"), and running SHA-256 hash seals.
- Dynamic QR verification code generated in-memory (`app/reports/seals.py`), embedding the case ID, evidence ID, primary SHA-256 hash, and examination timestamp.
- Verified with PyPDF integration tests confirming page structure, metadata dictionary, and PDF compliance.

---

## 8. Forensic Constraints & Legal Disclaimers

The following scientific and legal boundaries are documented in `docs/FORENSIC_LIMITATIONS.md` and enforced in system outputs:
- **Integrity vs Authenticity:** A verified SHA-256 hash proves that evidence bytes have not been altered since the moment of platform ingestion. It does not prove that the media was genuine or untampered prior to ingestion.
- **Investigative Heuristics:** Error Level Analysis (ELA), audio STFT anomalies, and metadata inconsistencies are investigative clues, not definitive proofs of tampering. Legitimate operations (e.g. repeated resaving, social media compression, transcoding) can cause ELA disparities.
- **Report Transparency:** Courtroom reports must explicitly delineate raw physical observations (metadata tags, spectrogram clipping) from forensic interpretations and limitations.

---

## 9. Confirmed Facts vs. Environment Constraints

| Topic | Status | Detail / Verification Evidence |
| :--- | :--- | :--- |
| **All 8 Phases Implemented** | **Confirmed Fact** | All 21 tasks in `TASK_TRACKER.md` verified. Full Pytest suite passes: 109 tests passed in 60.87s. |
| **Frontend Production Ready** | **Confirmed Fact** | Next.js 14 compiles cleanly (`npm run build`), generating all 9 routes. TypeScript typecheck clean (0 errors). |
| **Queue Engine** | **Confirmed Fact** | Engine is Redis Queue (RQ `2.x`), not Celery. Backed by PostgreSQL state mirroring. |
| **Local Host Docker Status** | **Environment Constraint** | Docker is not running in the Windows PATH on the local machine. All automated tests run safely using `aiosqlite` and `fakeredis`. Running the full multi-container stack with live PostgreSQL/Redis requires launching Docker Desktop. |
| **External CLI Binaries** | **Environment Constraint** | `exiftool` and `ffmpeg` are containerized in `services/api/Dockerfile`. To run live analysis directly on the Windows host outside Docker, ExifTool and FFmpeg must be placed on the host's `PATH`. |
