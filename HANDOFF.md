# PS-05 Project Handoff & Session Entry Point

> **Document Purpose:** Primary orientation document for a new AI account or coding agent taking over development of the Bihar Cyber Hackathon 2026 PS-05 platform.  
> **Order of Reading:** Read this document immediately after [AGENTS.md](file:///c:/Users/Basharat/Desktop/digital%20forensics/AGENTS.md).  
> **Last Verification Date:** 2026-10-25  
> **System Health:** 136 Backend Tests Passing (100%), Mypy Clean (102 files), Frontend Clean Build (9 routes)

---

## 1. Project Objective

Build a courtroom-admissible **Digital Evidence Authenticity and Integrity Verification Platform** for the Bihar Cyber Hackathon 2026 (Problem Statement PS-05). The platform enables forensic examiners and investigators to ingest digital evidence (images, audio, video), compute immediate multi-hash fingerprints, enforce immutable chain-of-custody logging via database triggers, perform automated deep forensic analysis (EXIF/metadata, JPEG ELA, OpenCV video cuts, audio STFT spectrograms), and generate verifiable courtroom PDF examination reports.

---

## 2. Current Verified Architecture

The platform is structured as a **modular monolith backend** paired with a **decoupled background worker fleet** and a **Next.js 14 investigative frontend**:

```
digital-forensics/
├── services/api/            # FastAPI Modular Monolith (Python 3.11+)
│   ├── app/main.py          # HTTP API entrypoint (FastAPI + ASGI)
│   ├── app/worker.py        # Asynchronous background worker (RQ)
│   ├── app/forensics/       # Deep forensic analysis engines (ELA, STFT, OpenCV, FFmpeg)
│   ├── app/queue/           # Redis Queue (RQ) integration & state mirroring
│   └── app/reports/         # ReportLab Platypus courtroom PDF generator
├── apps/web/                # Next.js 14 Investigative Web Console (App Router)
│   └── src/app/             # 9 production routes (dashboard, cases, evidence, analysis, reports)
├── storage/                 # Local private evidence vaults (git-ignored)
│   ├── originals/           # Bitstream originals (chmod 0400 read-only locked)
│   ├── artifacts/           # Derivative outputs (ELA heatmaps, spectrograms, frames)
│   ├── reports/             # Compiled PDF examination reports
│   └── tmp/                 # Ephemeral upload staging and scratch area
└── docker-compose.yml       # Production/development orchestration (PostgreSQL 16, Redis 7, API, Worker, Web)
```

---

## 3. Prompts 1–10 Completion Confirmation

All tasks requested across Prompts 1 through 10 have been completed and verified with automated test suites:

| Prompt / Milestone | Scope | Status | Verification Evidence |
| :--- | :--- | :---: | :--- |
| **Prompt 1 (Phase 1)** | Scaffolding, Docker Compose, Storage Paths & Health Probes | **Verified** | Storage paths initialized; `/api/v1/health` and `/ready` probes active |
| **Prompt 2 (Phase 2)** | SQLAlchemy 2.0 ORM Models, Alembic Migrations & DB Triggers | **Verified** | 8 domain entities; triggers block SQL UPDATE/DELETE on `audit_events` |
| **Prompt 3 (Phase 3)** | Multi-Hasher, Ingestion Service & Vault Permission Locking | **Verified** | Streaming SHA-256/SHA-1/MD5; two-phase commit; read-only lock `chmod 0400` |
| **Prompt 4 (Phase 4)** | Durable Redis Queue (RQ) Worker, ExifTool & FFprobe Adapters | **Verified** | Subprocess parameter injection mitigations; timeout enforcement; RQ jobs |
| **Prompt 5 (Phase 5)** | Deep Forensics: JPEG ELA, OpenCV Keyframes & SciPy Audio STFT | **Verified** | Difference heatmaps; video scene-cut detector; audio spectrogram & clipping |
| **Prompt 6 (Phase 6)** | Courtroom PDF Examination Report Builder with QR/Hash Seals | **Verified** | ReportLab Platypus layout; dynamic QR code; running header/footer seals |
| **Prompt 7 (Phase 7)** | Next.js 14 Investigative Dashboard & Interactive Visualizers | **Verified** | Dual-slider ELA viewer; STFT spectrogram player; video keyframe carousel |
| **Prompt 8 (Phase 8)** | System Hardening, Bit-Flip Tamper Simulation & Acceptance | **Verified** | Automated bit-flip detection tests pass; path traversal and injection tests pass |
| **Prompt 9 (Phase 5+)** | Video Evidence Analysis: FFprobe Stream Inspection & FFmpeg Frame Extraction | **Verified** | 19 video unit tests; bounded timestamps, resolution scaling, subprocess safety |
| **Prompt 10 (Phase 5+)** | Audio Evidence Analysis: FFprobe Metadata, FFmpeg Bounded Decoding & STFT | **Verified** | 14 audio unit tests; silence handling, clipping detection, lossy cutoff shelf, disclaimers |

**Summary Metrics:**
- **Backend Test Suite:** 136 tests passed in 94.98s (`python -m pytest services/api/tests -v`).
- **Backend Type Safety:** Mypy passed with zero errors across 102 source files.
- **Frontend Compilation:** Next.js 14 (`npm run build`) compiled successfully with all 9 static and dynamic routes.
- **Frontend Type Safety:** TypeScript typecheck clean with 0 errors (`npm run typecheck`).

---

## 4. Key Features Implemented

1. **Streaming Ingestion & Multi-Hashing:** Computes SHA-256 (forensic baseline), SHA-1, and MD5 simultaneously on incoming network streams without loading whole files into RAM.
2. **Atomic Two-Phase Vault Storage:** Files upload to `storage/tmp/` and atomically promote to `storage/originals/` upon database commit with read-only permission locking (`chmod 0400` / `stat.S_IREAD`). Rollback removes temporary files upon failure.
3. **Database-Level Anti-Tampering:** Dual-engine SQL triggers (PostgreSQL PL/pgSQL & SQLite) permanently abort any update or deletion of `audit_events` and any modification of `evidence_items.primary_hash_sha256`.
4. **Independent Cryptographic Re-Verification:** Reads disk bytes in 64KB chunks to verify against original SHA-256 baseline; bit-flips generate an immediate `TAMPER_DETECTED` audit alert.
5. **Durable Redis Queue (RQ) Fleet:** Background analysis tasks queued in Redis with authoritative lifecycle state mirrored in PostgreSQL. Includes worker startup crash recovery, watchdog sweeping, and retry finding deduplication.
6. **Forensic Analysis Engines:**
   - Sandboxed ExifTool & FFprobe wrappers with timeout and bounded output protection.
   - Pillow + NumPy Error Level Analysis (ELA) with normalized difference heatmaps.
   - OpenCV temporal analysis extracting scene cut timestamps, keyframes, and dHash fingerprints.
   - SciPy STFT generating frequency spectrograms, audio waveforms, and clipping anomaly detection.
7. **Courtroom PDF Examination Report Engine:** ReportLab Platypus generator with vector seals, running SHA-256 hash headers, and dynamic QR verification codes.
8. **Investigative Frontend Console:** Next.js 14 App Router UI with responsive case management, chunked uploads, dual-image comparison sliders, and synchronized media inspectors.

---

## 5. Important Files & Locations

| Subsystem | Primary Implementation File(s) | Primary Test File(s) |
| :--- | :--- | :--- |
| **HTTP API Monolith** | [services/api/app/main.py](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/app/main.py) | [tests/test_health.py](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/tests/test_health.py) |
| **API Routers (v1)** | [services/api/app/api/v1/](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/app/api/v1/) | [tests/test_auth_and_cases.py](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/tests/test_auth_and_cases.py) |
| **Database & Triggers** | [services/api/app/db/triggers.py](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/app/db/triggers.py) | [tests/integration/test_audit_immutability.py](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/tests/integration/test_audit_immutability.py) |
| **Storage & Multi-Hasher** | [services/api/app/storage/hasher.py](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/app/storage/hasher.py) | [tests/unit/test_hashing.py](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/tests/unit/test_hashing.py) |
| **Ingestion & Verification** | [services/api/app/services/evidence_service.py](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/app/services/evidence_service.py) | [tests/integration/test_tamper_detection.py](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/tests/integration/test_tamper_detection.py) |
| **RQ Worker Entrypoint** | [services/api/app/worker.py](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/app/worker.py) | [tests/integration/test_worker_queue.py](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/tests/integration/test_worker_queue.py) |
| **Forensic Adapters** | [services/api/app/forensics/](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/app/forensics/) | [tests/unit/test_forensic_adapters.py](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/tests/unit/test_forensic_adapters.py) |
| **ReportLab PDF Engine** | [services/api/app/reports/builder.py](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/app/reports/builder.py) | [tests/integration/test_courtroom_report.py](file:///c:/Users/Basharat/Desktop/digital%20forensics/services/api/tests/integration/test_courtroom_report.py) |
| **Frontend Console** | [apps/web/src/app/](file:///c:/Users/Basharat/Desktop/digital%20forensics/apps/web/src/app/) | TypeScript build & ESLint (`npm run build`) |

---

## 6. Known Environment Constraints & Inconsistencies

1. **Host Docker Status:**
   - The local Windows host does not have Docker Desktop running in PATH.
   - Automated tests run entirely in-memory using `aiosqlite` and `fakeredis`.
   - Running live multi-container deployments (`docker compose up`) requires starting Docker Desktop on the host.
2. **External CLI Tools on Host:**
   - `exiftool` and `ffmpeg` are containerized in `services/api/Dockerfile`.
   - If running the worker or API locally outside Docker, ExifTool and FFmpeg must be installed on the host's Windows PATH for full live media analysis.
3. **Queue Architecture Reconcile:**
   - Early planning documents (`docs/ADR.md` ADR-003) originally drafted Celery.
   - During Phase 4 implementation, the project adopted **Redis Queue (RQ 2.x)** for lightweight footprint, SimpleWorker compatibility on Windows, and PostgreSQL state mirroring.
   - Documentation has been reconciled in `PROJECT_CONTEXT.md` and `DECISIONS.md` (ADR-009).

---

## 7. Status of Current Task

**No active task is currently in progress.**  
The previous session concluded with all 23 roadmap tasks across Prompts 1–10 verified (136 passing tests).

When the user supplies a new development prompt (e.g. Prompt 11 or beyond):
1. Create a task plan in [CURRENT_TASK.md](file:///c:/Users/Basharat/Desktop/digital%20forensics/CURRENT_TASK.md).
2. Follow the operating constraints in [AGENTS.md](file:///c:/Users/Basharat/Desktop/digital%20forensics/AGENTS.md).
3. Verify test baseline before writing code.
