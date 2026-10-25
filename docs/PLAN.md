# PS-05 Digital Evidence Authenticity and Integrity Verification Platform Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an enterprise-grade, courtroom-admissible digital forensics platform for ingesting image, audio, and video evidence, computing immutable SHA-256 baseline hashes, executing forensic analyses (EXIF, JPEG ELA, video keyframes, audio spectrograms), maintaining an immutable chain-of-custody audit log, and compiling verifiable PDF reports.

**Architecture:** A modular monolith (FastAPI) paired with a decoupled asynchronous worker fleet (Celery + Redis), private local storage with storage provider abstraction, PostgreSQL for relational and immutable audit logging, and a Next.js (TypeScript + Tailwind CSS) investigative frontend. Strict layer separation ensures presentation, domain logic, persistence, storage, forensic engines, and report generation remain isolated and testable.

**Tech Stack:** Next.js, TypeScript, Tailwind CSS, Python 3.11+, FastAPI, SQLAlchemy 2.0 (Async), Alembic, PostgreSQL 16, Redis 7, Celery, ExifTool, FFmpeg/FFprobe, Pillow, OpenCV, NumPy, SciPy, librosa, ReportLab, Docker Compose.

---

### Implementation Roadmap Overview

| Phase | Milestone Name | Primary Focus | Output Artifacts |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Scaffolding & Core Infrastructure | Docker Compose, Backend skeleton, Redis, Postgres | Dev containers running, DB connected |
| **Phase 2** | Domain Entities & Audit Immutability | SQLAlchemy models, Alembic, PostgreSQL Triggers | Tables migrated, DB trigger anti-tamper tests |
| **Phase 3** | Storage Abstraction & Ingestion Engine | Streaming multi-hasher (SHA-256/SHA-1/MD5), Vault | Ingestion API, `0400` POSIX lock, baseline hashes |
| **Phase 4** | Durable Worker & Metadata Extraction | Celery tasks, ExifTool & FFprobe safe subprocesses | Task orchestration, JSONB metadata extract |
| **Phase 5** | Deep Forensic Analysis Engines | Pillow ELA, OpenCV video slicer, librosa audio DSP | ELA heatmaps, keyframe carousels, spectrograms |
| **Phase 6** | Courtroom PDF Report Engine | ReportLab Platypus, Hash Seals, Chain of Custody | Courtroom-ready PDF reports with QR & seals |
| **Phase 7** | Next.js Forensic Dashboard & Visualizers | Case management, upload progress, media viewers | Interactive UI, synchronized audio/spectrogram |
| **Phase 8** | System Hardening & End-to-End Acceptance | Security audits, bit-flip simulation, penetration test | Passing acceptance suites, verification report |

---

### Phase 1: Scaffolding, Docker Compose & Core Infrastructure

#### Purpose
Establish the multi-container development environment so all developers and automated tests run against identical system libraries (specifically Perl 5 for ExifTool, FFmpeg binary packages, and Python C-extensions).

#### Dependency Choices
- `docker-compose.yml` defining services: `backend`, `worker`, `frontend`, `db` (Postgres 16 Alpine), and `redis` (Redis 7 Alpine).
- Shared named volumes: `postgres_data`, `redis_data`, and `vault_storage` (simulating isolated private evidence storage).
- Python 3.11-slim base image with system dependencies: `ffmpeg`, `libsm6`, `libxext6`, `libgl1-mesa-glx`, `perl`, `exiftool`.

#### Data Flow
External HTTP requests reach FastAPI on port 8000; Celery connects to Redis on port 6379; FastAPI and Worker connect to PostgreSQL on port 5432; shared private storage mounted at `/storage`.

#### Tasks & Implementation Order

##### Task 1.1: Docker Compose & Base Environment
**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `docker/backend/Dockerfile`
- Create: `docker/worker/Dockerfile`

**Step 1:** Define `.env.example` containing `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, and `STORAGE_VAULT_ROOT`.  
**Step 2:** Write `docker/backend/Dockerfile` installing system dependencies (`ffmpeg`, `libimage-exiftool-perl`, `libsndfile1`), Python virtualenv, and project requirements.  
**Step 3:** Write `docker/worker/Dockerfile` targeting the same base image but configuring non-root user `forensic` (UID 10001).  
**Step 4:** Write `docker-compose.yml` linking all services with health checks on PostgreSQL and Redis.  
**Step 5:** Verify containers boot cleanly:
```bash
docker compose up -d db redis
docker compose ps
```

##### Task 1.2: Backend Modular Monolith Structure & FastAPI Skeleton
**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/requirements.txt`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/tests/conftest.py`

**Step 1: Write test for healthcheck endpoint**
```python
# backend/tests/test_health.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_system_health():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "OPERATIONAL"
```
**Step 2:** Run `pytest backend/tests/test_health.py` (Expected: FAIL).  
**Step 3:** Implement `backend/app/config.py` using `pydantic-settings` and `backend/app/main.py` with FastAPI router aggregation and CORS/Security headers.  
**Step 4:** Re-run `pytest backend/tests/test_health.py` (Expected: PASS).

#### Phase 1 Acceptance Tests
- [ ] `docker compose up -d` brings up `db` and `redis` with healthy status.
- [ ] Backend responds with HTTP 200 on `/api/v1/health` with `{"status": "OPERATIONAL"}`.
- [ ] System binaries (`ffmpeg -version`, `exiftool -ver`) are present and functional inside backend container.

---

### Phase 2: Domain Modeling, PostgreSQL Database & Immutable Audit Trigger

#### Purpose
Create the relational foundation for cases, evidence, analyses, artifacts, and audit logs. Enforce physical immutability at the database layer via PostgreSQL PL/pgSQL triggers to prevent evidence tampering or audit alteration.

#### Dependency Choices
- `SQLAlchemy 2.0` with `asyncpg` for non-blocking asynchronous database operations.
- `Alembic` for schema migrations.
- PostgreSQL `JSONB` data types for arbitrary raw EXIF and FFprobe metadata.

#### Data Flow
All state mutations (case creation, evidence registration, analysis logging) flow through SQLAlchemy async sessions. Any attempt to update or delete audit records is blocked at the database engine level by trigger execution.

#### Tasks & Implementation Order

##### Task 2.1: Database Engine & Scoped Async Session Factory
**Files:**
- Create: `backend/app/db/session.py`
- Create: `backend/app/db/base.py`

**Step 1:** Implement async engine with connection pooling and async context manager `get_db()`.  
**Step 2:** Write unit test verifying database connection checkout and rollback on exceptions.

##### Task 2.2: ORM Models (Case, EvidenceItem, HashVerification, AuditEvent, Reports)
**Files:**
- Create: `backend/app/db/models/user.py`
- Create: `backend/app/db/models/case.py`
- Create: `backend/app/db/models/evidence.py`
- Create: `backend/app/db/models/analysis.py`
- Create: `backend/app/db/models/audit.py`
- Create: `backend/app/db/models/report.py`

**Step 1:** Define SQLAlchemy 2.0 mapped models with explicit types, foreign keys, indexes, and unique constraints.  
**Step 2:** Model the `audit_events` table with `previous_state_hash` and `event_hash` columns for cryptographic chaining.

##### Task 2.3: Alembic Migration & Immutability Trigger Installation
**Files:**
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_initial_schema.py`
- Create: `backend/tests/integration/test_audit_immutability.py`

**Step 1: Write the failing anti-tamper test**
```python
# backend/tests/integration/test_audit_immutability.py
import pytest
from sqlalchemy import text
from app.db.session import async_session_factory

@pytest.mark.asyncio
async def test_audit_log_cannot_be_updated_or_deleted():
    async with async_session_factory() as session:
        # Insert audit record
        await session.execute(text(
            "INSERT INTO audit_events (id, event_type, action_description, event_hash) "
            "VALUES (gen_random_uuid(), 'EVIDENCE_INGESTED', 'Test action', 'hash123')"
        ))
        await session.commit()
        
        # Attempt update (Must raise Database Exception)
        with pytest.raises(Exception) as exc_info:
            await session.execute(text("UPDATE audit_events SET action_description = 'Tampered'"))
            await session.commit()
        assert "CRITICAL SECURITY VIOLATION" in str(exc_info.value)
```
**Step 2:** Run test (Expected: FAIL - trigger does not exist yet).  
**Step 3:** Implement migration script including the PL/pgSQL trigger `prevent_audit_tampering()`.  
**Step 4:** Run `alembic upgrade head`.  
**Step 5:** Re-run test (Expected: PASS).

#### Phase 2 Acceptance Tests
- [ ] Database schema deploys cleanly with zero errors via `alembic upgrade head`.
- [ ] SQL `UPDATE` or `DELETE` against `audit_events` is rejected with `CRITICAL SECURITY VIOLATION`.
- [ ] Direct SQL update of `primary_hash_sha256` on `evidence_items` is rejected by the database.

---

### Phase 3: Storage Provider Abstraction, Ingestion & Multi-Hashing

#### Purpose
Implement the secure ingestion boundary. Files must be streamed into the private vault while computing SHA-256, SHA-1, and MD5 digests concurrently, locking permissions to read-only (`0400`), registering evidence in the case, and writing an immutable audit record.

#### Dependency Choices
- Python `hashlib` (standard library, C-optimized).
- Custom `StreamingMultiHasher` wrapping `AsyncIterator[bytes]`.
- `LocalFilesystemStorageProvider` enforcing atomic file quarantine and POSIX permission stripping.

#### Data Flow
Incoming multipart byte stream -> MultiHasher (updates SHA-256, SHA-1, MD5 contexts in memory) -> Quarantine disk path -> Permission lock (`0400`) & Move to Vault -> Database record insertion -> Audit event emission with hash chain link.

#### Tasks & Implementation Order

##### Task 3.1: Streaming Multi-Hasher & Storage Provider
**Files:**
- Create: `backend/app/storage/base.py`
- Create: `backend/app/storage/local.py`
- Create: `backend/tests/unit/test_hashing.py`

**Step 1: Write streaming hash unit test**
```python
# backend/tests/unit/test_hashing.py
import pytest
import hashlib
from app.storage.hasher import MultiHasher

@pytest.mark.asyncio
async def test_streaming_multi_hasher():
    payload = b"Digital Forensic Evidence Stream Content 2026"
    hasher = MultiHasher()
    hasher.update(payload)
    digests = hasher.finalize()
    
    assert digests.sha256 == hashlib.sha256(payload).hexdigest()
    assert digests.md5 == hashlib.md5(payload).hexdigest()
    assert digests.sha1 == hashlib.sha1(payload).hexdigest()
    assert digests.byte_count == len(payload)
```
**Step 2:** Implement `MultiHasher` and `LocalFilesystemStorageProvider`.  
**Step 3:** Verify unit test passes.

##### Task 3.2: Evidence Ingestion Service & API Endpoint
**Files:**
- Create: `backend/app/services/evidence_service.py`
- Create: `backend/app/api/v1/evidence.py`
- Create: `backend/tests/integration/test_evidence_ingestion.py`

**Step 1:** Write integration test uploading an image file to `/api/v1/cases/{case_id}/evidence`.  
**Step 2:** Test asserts HTTP 201 Created, verifies database record exists, verifies physical file on disk has `0400` permissions, and verifies initial `hash_verifications` baseline is committed.  
**Step 3:** Implement `EvidenceService.ingest_evidence()` and the FastAPI router.  
**Step 4:** Run integration test and verify pass.

##### Task 3.3: Cryptographic Re-Verification Service
**Files:**
- Create: `backend/app/services/verification_service.py`
- Create: `backend/tests/integration/test_tamper_detection.py`

**Step 1:** Write test that intentionally modifies one byte in the physical file on disk using direct root OS call.  
**Step 2:** Run `VerificationService.verify_evidence_integrity(evidence_id)`.  
**Step 3:** Assert that the service detects the hash mismatch, logs a `CRITICAL_TAMPER_ALERT` in audit logs, and marks `is_intact = False`.

#### Phase 3 Acceptance Tests
- [ ] Multi-gigabyte file upload streams without exceeding 50 MB application RAM usage.
- [ ] Ingested files receive SHA-256, SHA-1, and MD5 digests matching independent OS `sha256sum`.
- [ ] Ingested files have file permissions set to `0400` (read-only).
- [ ] Intentional single-bit file modification triggers immediate tampering alert during verification.

---

### Phase 4: Durable Worker & Metadata Extraction Engine

#### Purpose
Establish the decoupled Celery background worker fleet with Redis to handle asynchronous processing. Integrate Phil Harvey's ExifTool and FFprobe in an isolated, sandboxed subprocess wrapper to extract deep metadata into PostgreSQL `JSONB`.

#### Dependency Choices
- `Celery 5.3+` with `redis` broker and backend.
- CLI subprocess invocation with argument protection and explicit execution timeouts.

#### Data Flow
FastAPI enqueues task `extract_metadata_task(evidence_id)` -> Redis queue -> Celery worker claims task -> Read-only file handle passed to ExifTool/FFprobe -> Structured JSON output sanitized -> Saved in `metadata_extracts` table -> Audit event recorded.

#### Tasks & Implementation Order

##### Task 4.1: Celery Worker Configuration & Task Orchestration
**Files:**
- Create: `backend/app/workers/celery_app.py`
- Create: `backend/app/workers/tasks.py`

**Step 1:** Configure Celery with JSON task serializer, prefetch multiplier = 1, `task_acks_late = True`, and worker memory limit (`--max-tasks-per-child=50`).  
**Step 2:** Implement base worker task with automated database session management and error handling.

##### Task 4.2: Sandboxed ExifTool & FFprobe Subprocess Wrappers
**Files:**
- Create: `backend/app/forensics/metadata_extractor.py`
- Create: `backend/tests/unit/test_metadata_extractor.py`

**Step 1: Write test for command injection safety**
```python
# backend/tests/unit/test_metadata_extractor.py
import pytest
from app.forensics.metadata_extractor import SafeMetadataExtractor

def test_exiftool_command_injection_mitigation():
    extractor = SafeMetadataExtractor()
    malicious_filename = "; cat /etc/passwd; --config"
    cmd = extractor.build_exiftool_command(malicious_filename)
    
    assert cmd[0] == "exiftool"
    assert "--" in cmd  # Ensures terminator separates flags from path
    assert malicious_filename == cmd[-1]
```
**Step 2:** Implement `SafeMetadataExtractor.extract_image_metadata()` and `extract_media_container_metadata()` using `subprocess.run(..., shell=False, timeout=30)`.  
**Step 3:** Implement JSON sanitization to handle unprintable binary MakerNotes characters.  
**Step 4:** Run unit and integration tests.

#### Phase 4 Acceptance Tests
- [ ] Celery worker boots and successfully connects to Redis broker.
- [ ] ExifTool extracts nested EXIF, IPTC, XMP, and camera serial numbers into structured JSON.
- [ ] FFprobe extracts codec profiles, duration, sample rate, and bitrate from video and audio containers.
- [ ] Subprocess execution enforces strict timeouts and drops malicious arguments without shell evaluation.

---

### Phase 5: Deep Forensic Analysis Engines

#### Purpose
Implement the core mathematical forensic analysis routines for image, video, and audio modalities, generating courtroom-grade analytical metrics and derivative visual artifacts (heatmaps, keyframes, spectrograms).

#### Dependency Choices
- **Image ELA:** Pillow (PIL) and NumPy.
- **Video Slicing:** FFmpeg and OpenCV (`cv2`).
- **Audio DSP:** `librosa`, `scipy.signal`, `soundfile`, `matplotlib` (headless `Agg` backend).

#### Modality Sub-Pipelines & Tasks

##### Task 5.1: JPEG Error Level Analysis (ELA) Engine
**Files:**
- Create: `backend/app/forensics/image_ela.py`
- Create: `backend/tests/unit/test_ela.py`

**Step 1:** Write unit test feeding known sample JPEG and verifying output artifact is a valid PNG heatmap.  
**Step 2:** Implement `ImageELAEngine.analyze()`:
- Re-save image at quality 95 in memory.
- Calculate difference: $|I_{\text{orig}} - I_{\text{resaved}}|$.
- Calculate scale factor: $\text{scale} = 255.0 / \max(\text{diff})$.
- Generate visual heatmap artifact with color mapping.
- Calculate block-level variance metrics (mean error, standard deviation, high-error outlier count).  
**Step 3:** Commit test and verify pass.

##### Task 5.2: Video Keyframe & Temporal Slicing Engine
**Files:**
- Create: `backend/app/forensics/video_analyzer.py`
- Create: `backend/tests/unit/test_video_analyzer.py`

**Step 1:** Write test extracting keyframes from sample video clip (`test.mp4`).  
**Step 2:** Implement `VideoAnalyzer.extract_keyframes()` using FFmpeg I-frame selector (`-vf "select='eq(pict_type,PICT_TYPE_I)'"`).  
**Step 3:** Implement OpenCV frame-difference loop to calculate scene changes and per-frame perceptual hashes (`dHash`).  
**Step 4:** Store extracted keyframe images in vault artifacts directory and index their timestamps.

##### Task 5.3: Audio Waveform & Mel-Spectrogram DSP Engine
**Files:**
- Create: `backend/app/forensics/audio_spectrogram.py`
- Create: `backend/tests/unit/test_audio_dsp.py`

**Step 1:** Write test loading `test.wav` and verifying generated spectrogram PNG and frequency metrics.  
**Step 2:** Implement `AudioForensicEngine.analyze()`:
- Load PCM audio using `soundfile` / `librosa` with sample rate normalization.
- Compute STFT with Hann window (n_fft=2048, hop_length=512).
- Generate Mel-spectrogram in decibel scale (`librosa.power_to_db`).
- Detect high-frequency cutoff (detecting lossy compression like 16 kHz MP3 shelf).
- Render color-graded spectrogram PNG via Matplotlib (`Agg` backend).
- Render RMS waveform envelope PNG.  
**Step 3:** Store derivative images in vault artifacts directory and return frequency analysis model.

#### Phase 5 Acceptance Tests
- [ ] ELA generates high-contrast heatmap showing localized compression difference matrices.
- [ ] Video analyzer extracts all intra-coded I-frames with accurate millisecond timestamps.
- [ ] Audio analyzer renders accurate frequency spectrogram and correctly identifies lossy spectral cutoffs.
- [ ] All derivative artifacts are saved to private storage with SHA-256 integrity hashes recorded in `analysis_artifacts`.

---

### Phase 6: Courtroom PDF Report Generation & Cryptographic Seal

#### Purpose
Assemble comprehensive, legally defensible, courtroom-ready forensic examination reports containing case information, examiner certifications, complete chain of custody, analysis findings, embedded visual artifacts, and a cryptographic verification seal.

#### Dependency Choices
- `ReportLab 4.x` (Platypus high-level layout, Paragraphs, Tables, KeepTogether, Image flowables).
- `qrcode` for generating document verification QR code seals.

#### Data Flow
ReportService aggregates case records + evidence metadata + analysis summaries + artifact paths -> ReportLab builds two-pass PDF -> Computes SHA-256 of resulting PDF file -> Saves in `/reports/{id}.pdf` -> Commits database record and audit event.

#### Tasks & Implementation Order

##### Task 6.1: ReportLab Layout Templates & Custom Canvas
**Files:**
- Create: `backend/app/reports/templates.py`
- Create: `backend/app/reports/components.py`
- Create: `backend/app/reports/seals.py`

**Step 1:** Implement custom `NumberedCanvas` tracking total page count for "Page X of Y" legal compliance.  
**Step 2:** Design styling palette: high-contrast legal typography, evidentiary borders, law enforcement / laboratory header blocks.  
**Step 3:** Implement `CryptographicSealFlowable` generating verification QR code and SHA-256 fingerprint badge.

##### Task 6.2: Report Assembler & ReportService
**Files:**
- Create: `backend/app/reports/generator.py`
- Create: `backend/app/services/report_service.py`
- Create: `backend/app/api/v1/reports.py`
- Create: `backend/tests/unit/test_report_builder.py`

**Step 1: Write unit test verifying PDF compilation**
```python
# backend/tests/unit/test_report_builder.py
import pypdf
from app.reports.generator import CourtroomReportBuilder

def test_courtroom_report_generation(sample_case_data):
    builder = CourtroomReportBuilder()
    pdf_bytes = builder.build_pdf(sample_case_data)
    
    assert pdf_bytes.startswith(b"%PDF-")
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    # Verify presence of case number and hash seal in text
    extracted_text = "".join([page.extract_text() for page in reader.pages])
    assert sample_case_data.case_number in extracted_text
    assert "CHAIN OF CUSTODY" in extracted_text
```
**Step 2:** Implement `CourtroomReportBuilder` assembling Case Summary, Evidence Inventory, Chain-of-Custody Chronology Table, and Forensic Analysis Exhibits with embedded heatmaps and spectrograms.  
**Step 3:** Implement API endpoint `POST /api/v1/cases/{case_id}/reports/generate`.  
**Step 4:** Run tests and verify PDF creation.

#### Phase 6 Acceptance Tests
- [ ] PDF generates deterministically with proper pagination ("Page X of Y"), running headers, and footers.
- [ ] Embedded ELA heatmaps, spectrograms, and keyframes render at high print resolution without distortion.
- [ ] Chain-of-custody table includes complete timestamped audit history and examiner names.
- [ ] Final PDF file is saved with recorded SHA-256 digest and logged in audit trail.

---

### Phase 7: Next.js Frontend Dashboard, Case Management & Media Visualizers

#### Purpose
Deliver a responsive, high-contrast, modern user interface in Next.js 14/15 (TypeScript + Tailwind CSS) for forensic investigators and examiners to manage cases, upload evidence with streaming progress, inspect interactive forensic visualizations, and export reports.

#### Dependency Choices
- `Next.js 14/15` App Router with React Server Components for authenticated views and Client Components for interactive media visualizers.
- `Tailwind CSS` with dark-mode optimized forensic theme (zinc/slate base with emerald security indicators and amber warning flags).
- `Lucide React` icons.
- `wavesurfer.js` or HTML5 Audio API for interactive audio playback synced to spectrograms.

#### Data Flow
User initiates upload -> Next.js streams directly to FastAPI `/api/v1/evidence` -> UI polls or receives WebSocket status updates as Celery processes analyses -> Interactive canvas components render ELA heatmaps, frame carousels, and spectrogram timelines.

#### Tasks & Implementation Order

##### Task 7.1: Frontend Scaffolding, Design Tokens & API Client
**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/app/layout.tsx`
- Create: `frontend/src/components/layout/AppHeader.tsx`

**Step 1:** Configure Next.js with TypeScript and Tailwind CSS.  
**Step 2:** Build API client with interceptors for authentication tokens and error formatting.  
**Step 3:** Implement application shell with navigation breadcrumbs and active case indicators.

##### Task 7.2: Case Management & Evidence Upload Views
**Files:**
- Create: `frontend/src/app/cases/page.tsx`
- Create: `frontend/src/app/cases/[caseId]/page.tsx`
- Create: `frontend/src/app/cases/[caseId]/upload/page.tsx`
- Create: `frontend/src/components/evidence/EvidenceUploader.tsx`

**Step 1:** Implement Case List view with search, status filters, and New Case modal.  
**Step 2:** Implement Case Detail view showing evidence inventory, chain-of-custody ledger, and report links.  
**Step 3:** Build `EvidenceUploader` component displaying upload percentage and displaying computed SHA-256 hash badge upon receipt.

##### Task 7.3: Interactive Forensic Visualizers
**Files:**
- Create: `frontend/src/components/forensics/ELAViewer.tsx`
- Create: `frontend/src/components/forensics/KeyframeCarousel.tsx`
- Create: `frontend/src/components/forensics/SpectrogramViewer.tsx`
- Create: `frontend/src/app/evidence/[evidenceId]/page.tsx`

**Step 1:** Implement `ELAViewer`: side-by-side synchronized zoom & pan comparing original image against the ELA heatmap artifact, with contrast slider.  
**Step 2:** Implement `KeyframeCarousel`: thumbnail strip with timestamp scrubbers and frame detail inspection.  
**Step 3:** Implement `SpectrogramViewer`: audio player with cursor tracking frequency energy and playback position across the spectrogram.

##### Task 7.4: Report Generation & Verification Modal
**Files:**
- Create: `frontend/src/app/cases/[caseId]/reports/page.tsx`
- Create: `frontend/src/components/reports/ReportPreviewModal.tsx`

**Step 1:** Implement report generation wizard allowing selection of specific evidence and analysis exhibits.  
**Step 2:** Build report preview and download card showing document SHA-256 seal and download button.

#### Phase 7 Acceptance Tests
- [ ] Case creation, evidence upload, and evidence listing operate seamlessly via web UI.
- [ ] Evidence uploader correctly renders live progress and displays calculated SHA-256 upon completion.
- [ ] ELA visualizer allows comparison between original image and difference heatmap.
- [ ] Audio player synchronizes playback audio with visual timeline.

---

### Phase 8: End-to-End System Testing & Security Hardening Verification

#### Purpose
Conduct full-pipeline integration tests, security threat mitigations, and compliance verification.

#### Tasks & Implementation Order

##### Task 8.1: Full Pipeline Integration Test
**Step 1:** Ingest image, video, and audio evidence via API.  
**Step 2:** Trigger EXIF extraction, ELA, video frame slicing, and audio spectrogram generation through background workers.  
**Step 3:** Wait for background tasks to reach `COMPLETED`.  
**Step 4:** Generate Courtroom PDF report.  
**Step 5:** Verify PDF report contains all computed findings and valid SHA-256 seals.

##### Task 8.2: Tamper Simulation Test Suite
**Step 1:** Execute scheduled hash re-verification on all evidence items; assert all return `is_intact = True`.  
**Step 2:** Introduce 1-bit flip in one evidence file directly via disk write.  
**Step 3:** Re-run verification; assert platform flags corrupted item and writes critical audit alert.  
**Step 4:** Execute SQL `UPDATE` against `audit_events`; verify Postgres trigger blocks modification.

#### Phase 8 Acceptance Tests
- [ ] 100% of integration test suite passes in Docker environment.
- [ ] Evidence tampering is detected and recorded in audit log within 500ms of verification execution.
- [ ] Zero unhandled exceptions or 500 errors in API logs under invalid input test suite.
