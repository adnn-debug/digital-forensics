# PS-05 Digital Evidence Platform — Task Tracker

> **Status Glossary:**
> - `Planned`: Task defined in roadmap, not yet begun.
> - `In Progress`: Actively under implementation.
> - `Blocked`: Cannot proceed due to unmet external dependency or blocker.
> - `Completed`: Implementation finished, pending full automated verification.
> - `Verified`: Code committed, automated tests passed, linting & type checks clean.

---

## Milestone Summary (Prompts 1–9)

| Milestone & Associated Prompt | Total Tasks | Verified | In Progress | Planned | Blocked |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Prompt 1 / Phase 1: Scaffolding & Core Infrastructure** | 2 | 2 | 0 | 0 | 0 |
| **Prompt 2 / Phase 2: Domain Modeling & Immutability Triggers** | 3 | 3 | 0 | 0 | 0 |
| **Prompt 3 / Phase 3: Storage Abstraction & Ingestion Engine** | 3 | 3 | 0 | 0 | 0 |
| **Prompt 4 / Phase 4: Durable Worker Fleet & Metadata Extraction** | 3 | 3 | 0 | 0 | 0 |
| **Prompt 5 / Phase 5: Deep Forensic Analysis Engines** | 3 | 3 | 0 | 0 | 0 |
| **Prompt 6 / Phase 6: Courtroom PDF Report Engine** | 2 | 2 | 0 | 0 | 0 |
| **Prompt 7 / Phase 7: Next.js 14 Forensic Dashboard** | 3 | 3 | 0 | 0 | 0 |
| **Prompt 8 / Phase 8: System Hardening & Acceptance** | 2 | 2 | 0 | 0 | 0 |
| **Prompt 9: Video Evidence Analysis (FFprobe & FFmpeg)** | 1 | 1 | 0 | 0 | 0 |
| **Prompt 10: Audio Evidence Analysis (FFprobe, FFmpeg & STFT)** | 1 | 1 | 0 | 0 | 0 |
| **Total** | **23** | **23** | **0** | **0** | **0** |

---

## Detailed Task Register

### Prompt 1 / Phase 1: Scaffolding & Core Infrastructure
*Objective: Create initial repository foundation with FastAPI modular monolith, Next.js web console, storage directories, configuration, health/readiness endpoints, Makefile, and Docker Compose.*

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-1.1** | Multi-container setup (Docker Compose, environment configs, Dockerfiles) | **Verified** | `docker-compose.yml`, `.env`, `docker/*` | None | Valid compose config; environment variables loaded via Pydantic Settings |
| **TASK-1.2** | FastAPI modular monolith skeleton, health/readiness probes, and storage paths | **Verified** | `services/api/app/main.py`, `services/api/app/core/*`, `services/api/tests/test_health.py` | TASK-1.1 | 12 tests passed; HTTP 200 on `/api/v1/health` and `/api/v1/ready` |

---

### Prompt 2 / Phase 2: Domain Modeling & Immutable Audit Triggers
*Objective: Implement SQLAlchemy 2.0 ORM models, Alembic migrations, scoped async sessions, and database-level anti-tamper triggers for audit immutability.*

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-2.1** | Scoped async session factory, engine configuration, and connectivity checks | **Verified** | `services/api/app/db/session.py`, `services/api/app/db/base.py` | TASK-1.2 | `check_db_connectivity()` verified in readiness probe test |
| **TASK-2.2** | SQLAlchemy 2.0 ORM domain entities (User, Case, EvidenceItem, HashVerification, MetadataExtract, ForensicAnalysis, AnalysisArtifact, AuditEvent, Report) | **Verified** | `services/api/app/db/models/*` | TASK-2.1 | `test_full_domain_lifecycle_and_relationships` passed (Pytest) |
| **TASK-2.3** | Alembic migration schema and database anti-tamper triggers (Postgres PL/pgSQL & SQLite) | **Verified** | `services/api/alembic/versions/0001_initial_schema.py`, `services/api/app/db/triggers.py`, `services/api/tests/integration/test_audit_immutability.py` | TASK-2.2 | `test_audit_immutability.py` (3 tests passed); triggers abort SQL UPDATE/DELETE on audit_events |

---

### Prompt 3 / Phase 3: Storage Provider Abstraction, Ingestion & Multi-Hashing
*Objective: Build streaming multi-hasher (SHA-256, SHA-1, MD5), two-phase staged storage transaction, read-only vault permission locking, and independent tamper detection.*

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-3.1** | Streaming multi-hasher (SHA-256/SHA-1/MD5), read-only permission locking, and StorageProvider abstraction | **Verified** | `services/api/app/storage/base.py`, `services/api/app/storage/hasher.py`, `services/api/app/storage/local.py`, `services/api/tests/unit/test_hashing.py` | TASK-2.3 | `test_hashing.py` (6 passed in 0.19s); read-only locking (`0400` POSIX / `stat.S_IREAD` Windows) verified |
| **TASK-3.2** | Evidence ingestion service and upload API endpoint with quarantine workflow | **Verified** | `services/api/app/services/evidence_service.py`, `services/api/app/api/v1/evidence.py`, `services/api/tests/integration/test_evidence_ingestion.py`, `services/api/tests/test_evidence_intake.py` | TASK-3.1 | `test_evidence_ingestion.py` (3 passed), `test_evidence_intake.py` (15 passed); two-phase staged commit verified |
| **TASK-3.3** | Cryptographic re-verification service and tamper detection alerting | **Verified** | `services/api/app/services/verification_service.py`, `services/api/tests/integration/test_tamper_detection.py` | TASK-3.2 | `test_tamper_detection.py` passed; bit-flip simulation triggers `TAMPER_DETECTED` audit alert |

---

### Prompt 4 / Phase 4: Durable Worker Fleet & Metadata Extraction Engine
*Objective: Build durable background job queue (Redis Queue / RQ) with PostgreSQL state mirroring, worker crash recovery, and sandboxed ExifTool and FFprobe adapters.*

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-4.1** | Durable background job queue with Redis transport & PostgreSQL state mirroring | **Verified** | `services/api/app/worker.py`, `services/api/app/queue/*`, `services/api/tests/integration/test_worker_queue.py` | TASK-2.3 | All worker queue tests passed (job dispatch, polling, retry reconciliation, crash recovery) |
| **TASK-4.2** | ExifTool sandboxed subprocess wrapper with timeout and JSON output sanitization | **Verified** | `services/api/app/forensics/exif_adapter.py`, `services/api/tests/unit/test_forensic_adapters.py` | TASK-4.1 | Command injection mitigation, timeout handling, and normal JPEG extraction verified |
| **TASK-4.3** | FFprobe multimedia container & stream analysis subprocess wrapper | **Verified** | `services/api/app/forensics/ffprobe_adapter.py`, `services/api/tests/unit/test_forensic_adapters.py` | TASK-4.1 | Audio/video stream extraction and bounded buffer handling verified |

---

### Prompt 5 / Phase 5: Deep Forensic Analysis Engines
*Objective: Implement deep media analysis engines: JPEG Error Level Analysis (ELA) with heatmaps, OpenCV video keyframe & scene change extraction, and SciPy audio STFT spectrogram analyzer.*

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-5.1** | JPEG Error Level Analysis (ELA) engine (Pillow + NumPy) and heatmap generation | **Verified** | `services/api/app/forensics/image_engine.py`, `services/api/tests/unit/test_image_engine.py` | TASK-4.1 | Untouched vs tampered JPEG ELA, artifact generation, zero-alteration of original verified |
| **TASK-5.2** | Video keyframe slicer and scene change detector (OpenCV temporal analysis) | **Verified** | `services/api/app/forensics/video_engine.py`, `services/api/tests/unit/test_video_engine.py` | TASK-4.1 | Keyframe indexing, dHash visual hashing, and scene cut detection verified |
| **TASK-5.3** | Audio STFT spectrogram and waveform analyzer (SciPy + Matplotlib) | **Verified** | `services/api/app/forensics/audio_engine.py`, `services/api/tests/unit/test_audio_engine.py` | TASK-4.1 | STFT spectral transform, clipping detection, and waveform PNG generation verified |

---

### Prompt 6 / Phase 6: Courtroom PDF Report Engine
*Objective: Build deterministic courtroom examination PDF report engine using ReportLab Platypus, embedded hash seals, dynamic QR verification codes, and chain of custody logs.*

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-6.1** | ReportLab Platypus document layout templates and legal metadata tables | **Verified** | `services/api/app/reports/builder.py`, `services/api/tests/unit/test_report_builder.py` | TASK-5.1 | Valid courtroom PDF generation with chain-of-custody table verified with PyPDF |
| **TASK-6.2** | Embedded cryptographic hash seals, QR verification codes, and chain of custody logs | **Verified** | `services/api/app/reports/seals.py`, `services/api/app/reports/canvas.py`, `services/api/tests/integration/test_courtroom_report.py` | TASK-6.1 | QR verification codes, running header/footer seals, and report download endpoint verified |

---

### Prompt 7 / Phase 7: Next.js 14 Forensic Dashboard & Visualizers
*Objective: Build Next.js 14 investigative web console with case/evidence management, chunked upload, interactive ELA heatmap viewer, audio waveform player, and video keyframes.*

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-7.1** | Case and evidence management views with chunked upload progress | **Verified** | `apps/web/src/app/cases/*`, `apps/web/src/app/upload/*` | TASK-3.2 | Next.js compilation, TypeScript types, and routing verified |
| **TASK-7.2** | Interactive ELA heatmap viewer with dual image comparison slider | **Verified** | `apps/web/src/app/cases/[caseId]/evidence/[evidenceId]/image-analysis/page.tsx` | TASK-5.1 | Image analysis UI with dual-image slider and finding drawers verified |
| **TASK-7.3** | Synchronized audio waveform/spectrogram player and video keyframe carousel | **Verified** | `apps/web/src/app/cases/[caseId]/evidence/[evidenceId]/*` | TASK-5.2, TASK-5.3 | Audio STFT view, video keyframe carousel, and report generator verified |

---

### Prompt 8 / Phase 8: System Hardening & End-to-End Acceptance
*Objective: End-to-end acceptance testing, automated bit-flip tamper detection simulation, path traversal security testing, and subprocess command injection protection.*

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-8.1** | Automated bit-flip tamper simulation and immediate detection acceptance test | **Verified** | `services/api/tests/integration/test_tamper_detection.py`, `services/api/tests/test_evidence_intake.py` | All previous | Bit-flip simulations on disk trigger audit alerts and invalidate verification |
| **TASK-8.2** | Security audit (path traversal, subprocess injection, DoS protection) | **Verified** | `services/api/tests/unit/test_forensic_adapters.py`, `services/api/tests/test_storage.py` | All previous | Subprocess parameter injection mitigations, path traversal mitigations, and file validation verified |

---

### Prompt 9: Video Evidence Analysis (FFprobe Stream Inspection & FFmpeg Frame Extraction)
*Objective: Implement video stream inspection (FFprobe) and bounded representative frame extraction (FFmpeg) with parameter injection safety, resource limits, artifact isolation, and partial error handling without claiming tamper proof.*

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-9.1** | FFprobe video stream inspection and FFmpeg bounded representative frame extraction adapter | **Verified** | `services/api/app/forensics/ffmpeg_adapter.py`, `services/api/app/forensics/ffprobe_adapter.py`, `services/api/app/forensics/video_engine.py`, `services/api/app/queue/tasks.py`, `services/api/tests/unit/test_ffmpeg_adapter.py`, `services/api/tests/unit/test_video_engine.py` | TASK-4.3, TASK-5.2 | 19 video tests passed (`test_ffmpeg_adapter.py` and `test_video_engine.py`); bounded frame sampling, resolution bounding, subprocess argument list injection resistance, 0-byte/corrupt handling, and provenance recording verified. |

---

### Prompt 10: Audio Evidence Analysis (FFprobe, FFmpeg & STFT Spectrogram/Waveform)
*Objective: Implement audio stream inspection (FFprobe), bounded controlled decoding (FFmpeg), acoustic amplitude/clipping detection, STFT spectral metrics and low-pass cutoff detection, courtroom PNG artifact rendering, silent/truncated/oversized handling, and forensic disclaimer enforcement.*

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-10.1** | FFprobe audio stream inspection, FFmpeg bounded PCM decoding, and AudioForensicsEngine | **Verified** | `services/api/app/forensics/ffprobe_adapter.py`, `services/api/app/forensics/ffmpeg_adapter.py`, `services/api/app/forensics/audio_engine.py`, `services/api/app/queue/tasks.py`, `services/api/tests/unit/test_audio_engine.py` | TASK-4.3, TASK-5.3 | 14 audio tests passed in `test_audio_engine.py`; 136 full backend test suite passed; bounded decoding, silence handling, clipping detection, lossy shelf detection, 0-byte/oversized handling, and courtroom disclaimers verified. |

