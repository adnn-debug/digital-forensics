# PS-05 Digital Evidence Platform — Task Tracker

> **Status Glossary:**
> - `Planned`: Task defined in roadmap, not yet begun.
> - `In Progress`: Actively under implementation.
> - `Blocked`: Cannot proceed due to unmet external dependency or blocker.
> - `Completed`: Implementation finished, pending full automated verification.
> - `Verified`: Code committed, automated tests passed, linting & type checks clean.

---

## Milestone Summary

| Milestone | Total Tasks | Verified | Completed (fresh verification pending) | In Progress | Planned | Blocked |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Phase 1: Scaffolding & Core Infrastructure** | 2 | 0 | 2 | 0 | 0 | 0 |
| **Phase 2: Domain Modeling & Immutability Triggers** | 3 | 0 | 3 | 0 | 0 | 0 |
| **Phase 3: Storage Abstraction & Ingestion Engine** | 3 | 0 | 3 | 0 | 0 | 0 |
| **Phase 4: Durable Worker & Metadata Extraction** | 3 | 0 | 3 | 0 | 0 | 0 |
| **Phase 5: Deep Forensic Analysis Engines** | 3 | 0 | 3 | 0 | 0 | 0 |
| **Phase 6: Courtroom PDF Report Engine** | 2 | 0 | 2 | 0 | 0 | 0 |
| **Phase 7: Next.js Forensic Dashboard** | 3 | 0 | 3 | 0 | 0 | 0 |
| **Phase 8: System Hardening & Acceptance** | 2 | 0 | 2 | 0 | 0 | 0 |
| **Phase 9: Production Deployment & Acceptance** | 4 | 0 | 0 | 0 | 1 | 3 |
| **Total** | **25** | **0** | **21** | **0** | **1** | **3** |

---

**Verification note:** The evidence descriptions below are historical notes from the project tracker, not a fresh pass on this hardening branch. This branch has not yet produced a runnable CI result. Accordingly, tasks are marked **Completed** (implementation present; verification pending), not **Completed**. Move a task to **Completed** only after current-branch tests, linting, and type checks pass.

## Detailed Task Register

### Phase 1: Scaffolding & Core Infrastructure

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-1.1** | Multi-container setup (Docker Compose, environment configs, Dockerfiles) | **Completed** | `docker-compose.yml`, `.env`, `docker/*` | None | Files present, `.env` configured, Docker Compose valid syntax |
| **TASK-1.2** | FastAPI modular monolith skeleton, health/readiness probes, and storage paths | **Completed** | `services/api/app/main.py`, `services/api/app/core/*`, `services/api/tests/test_health.py` | TASK-1.1 | Pytest: 12 tests passed; HTTP 200 on `/api/v1/health` and `/api/v1/ready` |

---

### Phase 2: Domain Modeling & Immutable Audit Triggers

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-2.1** | Scoped async session factory, engine configuration, and connectivity checks | **Completed** | `services/api/app/db/session.py`, `services/api/app/db/base.py` | TASK-1.2 | `check_db_connectivity()` verified in readiness probe test |
| **TASK-2.2** | SQLAlchemy 2.0 ORM domain entities (User, Case, EvidenceItem, HashVerification, MetadataExtract, ForensicAnalysis, AnalysisArtifact, AuditEvent, Report) | **Completed** | `services/api/app/db/models/*` | TASK-2.1 | `test_full_domain_lifecycle_and_relationships` passed (Pytest) |
| **TASK-2.3** | Alembic migration schema and database anti-tamper triggers (Postgres PL/pgSQL & SQLite) | **Completed** | `services/api/alembic/versions/0001_initial_schema.py`, `services/api/app/db/triggers.py`, `services/api/tests/integration/test_audit_immutability.py` | TASK-2.2 | `test_audit_immutability.py` (3 tests passed); Ruff and Mypy passed |

---

### Phase 3: Storage Provider Abstraction, Ingestion & Multi-Hashing

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-3.1** | Streaming multi-hasher (SHA-256/SHA-1/MD5), read-only permission locking, and StorageProvider abstraction | **Completed** | `services/api/app/storage/base.py`, `services/api/app/storage/hasher.py`, `services/api/app/storage/local.py`, `services/api/tests/unit/test_hashing.py` | TASK-2.3 | `test_hashing.py` (6 passed in 0.19s); read-only locking (`0400` POSIX / `stat.S_IREAD` Windows) verified |
| **TASK-3.2** | Evidence ingestion service and upload API endpoint with quarantine workflow | **Completed** | `services/api/app/services/evidence_service.py`, `services/api/app/api/v1/evidence.py`, `services/api/tests/integration/test_evidence_ingestion.py`, `services/api/tests/test_evidence_intake.py` | TASK-3.1 | `test_evidence_ingestion.py` (3 passed), `test_evidence_intake.py` (15 passed); two-phase staged commit verified |
| **TASK-3.3** | Cryptographic re-verification service and tamper detection alerting | **Completed** | `services/api/app/services/verification_service.py`, `services/api/tests/integration/test_tamper_detection.py` | TASK-3.2 | `test_tamper_detection.py` passed; bit-flip simulation triggers `TAMPER_DETECTED` audit alert |

---

### Phase 4: Durable Worker & Metadata Extraction Engine

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-4.1** | Durable background job queue with Redis transport & PostgreSQL state mirroring | **Completed** | `services/api/app/worker.py`, `services/api/app/queue/*`, `services/api/tests/integration/test_worker_queue.py` | TASK-2.3 | All worker queue tests passed (job dispatch, polling, retry reconciliation, crash recovery) |
| **TASK-4.2** | ExifTool sandboxed subprocess wrapper with timeout and JSON output sanitization | **Completed** | `services/api/app/forensics/exif_adapter.py`, `services/api/tests/unit/test_forensic_adapters.py` | TASK-4.1 | Command injection mitigation, timeout handling, and normal JPEG extraction verified |
| **TASK-4.3** | FFprobe multimedia container & stream analysis subprocess wrapper | **Completed** | `services/api/app/forensics/ffprobe_adapter.py`, `services/api/tests/unit/test_forensic_adapters.py` | TASK-4.1 | Audio/video stream extraction and bounded buffer handling verified |

---

### Phase 5: Deep Forensic Analysis Engines

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-5.1** | JPEG Error Level Analysis (ELA) engine (Pillow + NumPy) and heatmap generation | **Completed** | `services/api/app/forensics/image_engine.py`, `services/api/tests/unit/test_image_engine.py` | TASK-4.1 | Untouched vs tampered JPEG ELA, artifact generation, zero-alteration of original verified |
| **TASK-5.2** | Video keyframe slicer and scene change detector (OpenCV temporal analysis) | **Completed** | `services/api/app/forensics/video_engine.py`, `services/api/tests/unit/test_video_engine.py` | TASK-4.1 | Keyframe indexing, dHash visual hashing, and scene cut detection verified |
| **TASK-5.3** | Audio STFT spectrogram and waveform analyzer (SciPy + Matplotlib) | **Completed** | `services/api/app/forensics/audio_engine.py`, `services/api/tests/unit/test_audio_engine.py` | TASK-4.1 | STFT spectral transform, clipping detection, and waveform PNG generation verified |

---

### Phase 6: Courtroom PDF Report Engine

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-6.1** | ReportLab Platypus document layout templates and legal metadata tables | **Completed** | `services/api/app/reports/builder.py`, `services/api/tests/unit/test_report_builder.py` | TASK-5.1 | Valid courtroom PDF generation with chain-of-custody table verified with PyPDF |
| **TASK-6.2** | Embedded cryptographic hash seals, QR verification codes, and chain of custody logs | **Completed** | `services/api/app/reports/seals.py`, `services/api/app/reports/canvas.py`, `services/api/tests/integration/test_courtroom_report.py` | TASK-6.1 | QR verification codes, running header/footer seals, and report download endpoint verified |

---

### Phase 7: Next.js Forensic Dashboard & Visualizers

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-7.1** | Case and evidence management views with chunked upload progress | **Completed** | `apps/web/src/app/cases/*`, `apps/web/src/app/upload/*` | TASK-3.2 | Next.js compilation, TypeScript types, and routing verified |
| **TASK-7.2** | Interactive ELA heatmap viewer with dual image comparison slider | **Completed** | `apps/web/src/app/cases/[caseId]/evidence/[evidenceId]/image-analysis/page.tsx` | TASK-5.1 | Image analysis UI with dual-image slider and finding drawers verified |
| **TASK-7.3** | Synchronized audio waveform/spectrogram player and video keyframe carousel | **Completed** | `apps/web/src/app/cases/[caseId]/evidence/[evidenceId]/*` | TASK-5.2, TASK-5.3 | Audio STFT view, video keyframe carousel, and report generator verified |

---

### Phase 8: System Hardening & End-to-End Acceptance

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-8.1** | Automated bit-flip tamper simulation and immediate detection acceptance test | **Completed** | `services/api/tests/integration/test_tamper_detection.py`, `services/api/tests/test_evidence_intake.py` | All previous | Bit-flip simulations on disk trigger audit alerts and invalidate verification |
| **TASK-8.2** | Security audit (path traversal, subprocess injection, DoS protection) | **Completed** | `services/api/tests/unit/test_forensic_adapters.py`, `services/api/tests/test_storage.py` | All previous | Subprocess parameter injection mitigations, path traversal mitigations, and file validation verified |


---

### Phase 9: Production Deployment & Acceptance

| Task ID | Task Description | Status | Related Files | Dependencies | Verification Evidence / Blocker |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **TASK-9.1** | Obtain a trustworthy green CI run for the exact release commit | **Blocked** | `.github/workflows/ci.yml`, tests | Actions must execute jobs | GitHub currently reports failed workflow runs with zero jobs; no reliable suite result is available |
| **TASK-9.2** | Choose and implement durable production evidence storage shared by API and worker | **Blocked** | `services/api/app/storage/*`, `docs/DEPLOYMENT_READINESS.md` | Hosting topology decision | Current adapter is local filesystem; production cannot use ephemeral container storage, and separate services must share the same durable namespace |
| **TASK-9.3** | Select hosting target, provision secrets/DB/Redis, and deploy over HTTPS | **Planned** | `docker-compose.yml`, deployment configuration | Hosting target and storage strategy | No verified public deployment URL or production configuration is recorded in this branch |
| **TASK-9.4** | Run end-to-end acceptance on the deployed server, including tamper detection and QR verification | **Blocked** | API, web UI, worker, reports | TASK-9.1 through TASK-9.3 | No deployment smoke test has been run; require intact and tampered file cases, worker execution, health/readiness, and backup/restore checks |
