# PS-05 Digital Evidence Authenticity & Integrity Verification Platform
## Architecture Decision Records (ADRs)

**Status:** Canonical Decision Log  
**Scope:** Architectural, Technical, and Evidentiary Design Decisions  

---

### Index of Records

- [ADR-001: Modular Monolith with Decoupled Worker Fleet](#adr-001-modular-monolith-with-decoupled-worker-fleet)
- [ADR-002: Backend Runtime, Async Ecosystem, and Type Validation](#adr-002-backend-runtime-async-ecosystem-and-type-validation)
- [ADR-003: Durable Asynchronous Task Queue & Broker](#adr-003-durable-asynchronous-task-queue--broker)
- [ADR-004: Storage Provider Abstraction & Evidence Immutability](#adr-004-storage-provider-abstraction--evidence-immutability)
- [ADR-005: Hybrid Forensic Tooling Strategy (Subprocess vs Native Python)](#adr-005-hybrid-forensic-tooling-strategy-subprocess-vs-native-python)
- [ADR-006: Programmatic PDF Report Engine (ReportLab vs Headless Chromium)](#adr-006-programmatic-pdf-report-engine-reportlab-vs-headless-chromium)
- [ADR-007: Cryptographic Hash Chaining & DB Triggers for Audit Immutability](#adr-007-cryptographic-hash-chaining--db-triggers-for-audit-immutability)

---

### ADR-001: Modular Monolith with Decoupled Worker Fleet

#### Context
The PS-05 platform requires tight integration between evidence ingestion, case management, chain-of-custody tracking, and analytical execution. We evaluated three architectural styles:
1. Microservices architecture (separate services for Auth, Ingestion, Metadata, Forensics, Reporting).
2. Pure single-process monolith (running HTTP API and forensic analyses within the same runtime).
3. Modular monolith with decoupled worker processes sharing a common core domain model.

#### Decision
We adopt the **Modular Monolith with Decoupled Worker Fleet** architecture. All code lives within a single well-structured backend repository with clear bounded contexts (api, services, domain, db, storage, forensics, reports, workers). A separate long-running worker process (or fleet of worker containers) pulls computational tasks from a Redis queue.

#### Alternatives Considered
- *Microservices:* Rejected due to excessive operational overhead, network latency when passing multi-gigabyte media payloads over internal RPCs, distributed transaction complexity, and premature optimization for a digital forensics platform.
- *Single-process Monolith:* Rejected because heavy CPU-bound tasks (FFmpeg video slicing, librosa STFT transforms) would saturate the Python GIL or event loop, causing HTTP timeouts and dropped connections.

#### Consequences
- **Positive:** Single deployment artifact for backend logic, zero internal network overhead for shared database access, strict separation of HTTP web requests from intensive CPU computation.
- **Negative:** Requires disciplined enforcement of module boundaries within the codebase to prevent cross-domain coupling.

---

### ADR-002: Backend Runtime, Async Ecosystem, and Type Validation

#### Context
The backend must handle high-throughput file stream ingestion (multi-gigabyte video files) concurrently without blocking worker threads, while maintaining strict typing and automated validation for complex forensic metadata.

#### Decision
We choose **Python 3.11+**, **FastAPI**, **SQLAlchemy 2.0 (Async mode with `asyncpg`)**, and **Pydantic v2**.

#### Alternatives Considered
- *Django & Django REST Framework:* Solid ORM, but lacks native async streaming capabilities and has high boilerplate for modern forensic pipelines.
- *Go (Golang):* Superb performance and concurrency, but lacks mature native digital forensics and audio DSP libraries (librosa, SciPy, Pillow, Matplotlib are Python-native).
- *Node.js / NestJS:* Excellent async I/O, but lacks high-precision scientific DSP and image manipulation ecosystems.

#### Consequences
- **Positive:** FastAPI provides native ASGI streaming, automated OpenAPI documentation, and sub-millisecond serialization via Pydantic v2 (Rust core). Native compatibility with Python's scientific computing libraries.
- **Negative:** Python requires careful memory management when processing large binary arrays in workers (addressed by worker recycling).

---

### ADR-003: Durable Asynchronous Task Queue & Broker

#### Context
Forensic analyses can take anywhere from 500 milliseconds (EXIF parsing) to 20 minutes (4K video keyframe decomposition). If a worker process fails midway, job state must be preserved, and examiners must be able to track granular task progress.

#### Decision
We choose **Celery** with **Redis 7.x** as the message broker, combined with **PostgreSQL transactional state mirroring**.

#### Alternatives Considered
- *ARQ (Async Redis Queue):* Lightweight and modern asyncio-native, but lacks mature worker process recycling (`max-tasks-per-child`), fine-grained subtask routing, and extensive production operational tooling.
- *RQ (Redis Queue):* Simple, but uses synchronous workers with forking models that are less flexible for high-concurrency tasks.
- *RabbitMQ + Celery:* Superior AMQP guarantees, but Redis is already needed for caching and session state. Using Redis simplifies local Docker Compose development while satisfying all durable queuing requirements.

#### Consequences
- **Positive:** Battle-tested task orchestration, automatic retries with exponential backoff, worker concurrency configuration, and hard/soft timeout enforcement.
- **Negative:** Celery task signatures require explicit serialization (JSON only; no arbitrary Python pickling for security).

---

### ADR-004: Storage Provider Abstraction & Evidence Immutability

#### Context
Evidence files require strict isolation and write-prohibition. Phase 1 targets private local filesystem storage (ideal for air-gapped lab deployments or local Docker development). Phase 2 requires enterprise cloud/object storage (MinIO or AWS S3 with Object Lock WORM).

#### Decision
We introduce an explicit `StorageProvider` abstraction interface (`app/storage/base.py`). The initial implementation is `LocalFilesystemStorageProvider`, designed to immediately apply POSIX `chmod 0400` (read-only) upon ingestion. The interface defines streaming primitives (`put_stream`, `get_stream`, `get_local_path_readonly`) to ensure seamless transition to `S3CompatibleStorageProvider`.

#### Alternatives Considered
- *Direct File System I/O:* Rejected because hardcoding `open('/var/data/...')` throughout services creates deep technical debt and prevents cloud migration.
- *Direct S3-only requirement:* Rejected because forensic laboratories often operate completely air-gapped without external cloud dependencies.

#### Consequences
- **Positive:** Absolute portability between air-gapped forensic workstations, on-prem servers, and cloud infrastructure.
- **Negative:** Streaming through the storage abstraction introduces a minor abstraction layer that must be maintained across all file operations.

---

### ADR-005: Hybrid Forensic Tooling Strategy (Subprocess vs Native Python)

#### Context
Forensic analysis requires a mixture of metadata extraction (EXIF, container atoms) and mathematical/signal-processing algorithms (ELA, STFT spectrograms, keyframe histograms).

#### Decision
We adopt a **hybrid execution strategy**:
1. **Sandboxed Subprocess Execution:** Used for Phil Harvey's **ExifTool** and **FFmpeg/FFprobe**. These tools are executed as isolated CLI subprocesses using `subprocess.run(shell=False)` with argument sanitation, non-root user execution, and hard timeouts.
2. **Native Python Scientific Pipelines:** Used for **Error Level Analysis (Pillow + NumPy)**, **Video Frame Slicing (OpenCV)**, and **Audio Spectrograms (librosa + SciPy)**. These run natively in the Python worker process for direct pixel and PCM array access without IPC serialization overhead.

#### Alternatives Considered
- *Native Python EXIF Parsers (e.g. `exifread`, `piexif`):* Rejected because they support only a fraction of the 25,000+ metadata tags that ExifTool parses (including proprietary camera MakerNotes and video container atoms).
- *Subprocess-only for everything:* Running Python scripts as subprocesses for ELA or DSP would introduce substantial cold-start overhead (loading NumPy/librosa imports repeatedly).

#### Consequences
- **Positive:** Best-in-class metadata extraction capability combined with high-performance in-memory matrix computations.
- **Negative:** Docker images must include Perl (for ExifTool) and FFmpeg system binaries alongside Python dependencies.

---

### ADR-006: Programmatic PDF Report Engine (ReportLab vs Headless Chromium)

#### Context
Forensic examination reports must be courtroom-admissible documents containing case metadata, chain-of-custody logs, examiner signatures, cryptographic hash seals, and embedded high-resolution visual evidence (ELA heatmaps, spectrograms).

#### Decision
We choose **ReportLab (Platypus architecture)** for programmatic PDF generation.

#### Alternatives Considered
- *Headless Chromium (Puppeteer / Playwright / WeasyPrint):* Generating HTML/CSS and printing via browser can look modern, but headless browsers consume substantial RAM (500MB+ per render), introduce non-deterministic page breaking, and introduce huge security attack surfaces (Chromium sandbox escapes).
- *LaTeX:* Superb typesetting, but requires heavy multi-gigabyte TeX distributions and is cumbersome to integrate programmatically with dynamic image artifacts.

#### Consequences
- **Positive:** Extremely lightweight, deterministic page-budget calculations, native vector graphics and barcode/QR generation, zero external browser runtime vulnerabilities, and byte-exact reproducibility.
- **Negative:** ReportLab Platypus requires imperative Python styling and layout declarations rather than web CSS.

---

### ADR-007: Cryptographic Hash Chaining & DB Triggers for Audit Immutability

#### Context
A primary defense challenge in court is proving that digital evidence records or audit logs were not altered or backdated in the database by a compromised system administrator or malicious insider.

#### Decision
We implement a **dual-layer immutability defense**:
1. **PostgreSQL Database Triggers:** Installed at migration time, triggers explicitly abort any `UPDATE` or `DELETE` query executed against the `audit_events` table or critical hash columns of `evidence_items`.
2. **Cryptographic HMAC Hash Chaining:** Every audit row includes the SHA-256 digest of the prior row, creating an unbroken cryptographic sequence.

#### Alternatives Considered
- *External Blockchain / Ledger Service (e.g. Amazon QLDB):* Unnecessary operational cost, vendor lock-in, and dependency on external cloud providers unsuitable for air-gapped forensic labs.
- *Application-only read-only enforcement:* Insufficient because any application vulnerability or direct DB access could bypass application-layer checks.

#### Consequences
- **Positive:** Legally defensible, mathematically verifiable chain of custody satisfying FRE 902(14) self-authentication requirements.
- **Negative:** Requires structured migration procedures; database records can never be pruned without archiving the entire database volume.
