# PS-05 Digital Evidence Platform — Architecture Decision Records (ADRs)

> **Scope:** Canonical record of architectural, cryptographic, and operational engineering decisions.  
> **Source Documents:** Derived from `docs/ADR.md` and verified codebase implementations.

---

## Index of Records

- [ADR-001: Modular Monolith with Decoupled Worker Fleet](#adr-001-modular-monolith-with-decoupled-worker-fleet)
- [ADR-002: Backend Runtime, Async Ecosystem, and Type Validation](#adr-002-backend-runtime-async-ecosystem-and-type-validation)
- [ADR-003: Durable Asynchronous Task Queue & Broker](#adr-003-durable-asynchronous-task-queue--broker)
- [ADR-004: Storage Provider Abstraction & Evidence Immutability](#adr-004-storage-provider-abstraction--evidence-immutability)
- [ADR-005: Hybrid Forensic Tooling Strategy (Subprocess vs Native Python)](#adr-005-hybrid-forensic-tooling-strategy-subprocess-vs-native-python)
- [ADR-006: Programmatic PDF Report Engine (ReportLab vs Headless Chromium)](#adr-006-programmatic-pdf-report-engine-reportlab-vs-headless-chromium)
- [ADR-007: Cryptographic Hash Chaining & DB Triggers for Audit Immutability](#adr-007-cryptographic-hash-chaining--db-triggers-for-audit-immutability)
- [ADR-008: Dual-Engine SQLite/PostgreSQL Database Anti-Tamper Triggers](#adr-008-dual-engine-sqlitepostgresql-database-anti-tamper-triggers)

---

### ADR-001: Modular Monolith with Decoupled Worker Fleet

- **Date:** 2026-10 (Initial Architecture Phase)
- **Status:** Accepted
- **Decision & Context:**
  Adopt a modular monolith backend architecture where all domain logic lives within a single well-structured Python repository, paired with decoupled worker processes pulling compute-heavy tasks from a Redis queue.
- **Reasoning:**
  Forensic investigations require transactional coordination between case management, ingestion, and chain of custody, but media processing (decoding 4K video, audio STFT) is CPU-intensive. Running tasks inside the HTTP event loop would saturate the runtime and drop connections. Microservices would introduce substantial operational overhead, network serialization bottlenecks for gigabyte-scale media, and distributed transaction complexity.
- **Alternatives Considered:**
  1. *Microservices Architecture:* Rejected due to excessive operational overhead and multi-gigabyte network transfer latency over internal RPCs.
  2. *Single-Process Monolith:* Rejected because CPU-bound forensics would block the Python GIL and event loop.
- **Consequences:**
  - *Positive:* High developer velocity, single deployment artifact for business logic, zero network overhead for database operations, and complete isolation of CPU spikes from HTTP clients.
  - *Implications:* Codebase conventions must strictly enforce layer separation (`api`, `services`, `domain`, `db`, `storage`, `forensics`, `reports`).

---

### ADR-002: Backend Runtime, Async Ecosystem, and Type Validation

- **Date:** 2026-10
- **Status:** Accepted
- **Decision & Context:**
  Use Python 3.11+, FastAPI, SQLAlchemy 2.0 (Async mode with `asyncpg`), and Pydantic v2 for the backend API and domain layer.
- **Reasoning:**
  FastAPI offers high asynchronous I/O performance via Starlette/uvicorn, automated OpenAPI generation, and strict type safety with Pydantic v2 (Rust-backed serialization). Python is the premier language for scientific computing, image processing (Pillow, OpenCV), and digital signal processing (librosa, SciPy).
- **Alternatives Considered:**
  1. *Django / Django REST Framework:* Lacks native async streaming capabilities and introduces unnecessary ORM overhead for forensic pipelines.
  2. *Go (Golang):* Excellent raw concurrency, but lacks mature digital forensics and scientific audio DSP ecosystems.
  3. *Node.js / NestJS:* Excellent async I/O, but lacks scientific DSP and pixel matrix manipulation libraries.
- **Consequences:**
  - *Positive:* Native support for async multipart file streaming, sub-millisecond serialization, and direct access to scientific libraries.
  - *Implications:* Memory must be managed carefully in worker child processes when processing large binary arrays (handled via worker task limits).

---

### ADR-003: Durable Asynchronous Task Queue & Broker

- **Date:** 2026-10
- **Status:** Accepted
- **Decision & Context:**
  Use Celery with Redis 7.x as message broker, combined with PostgreSQL transactional state mirroring.
- **Reasoning:**
  Forensic analyses vary from sub-second metadata parses to 20-minute video analyses. Worker recycling (`max-tasks-per-child=50`) is required to reclaim unmanaged memory from C-extensions (OpenCV, librosa). Redis satisfies both queuing and cache requirements without adding extra infrastructure components.
- **Alternatives Considered:**
  1. *ARQ (Async Redis Queue):* Lightweight, but lacks native worker process recycling (`max-tasks-per-child`) and task routing flexibility.
  2. *RabbitMQ + Celery:* Superior AMQP guarantees, but introduces additional container infrastructure when Redis is already required for session caching.
- **Consequences:**
  - *Positive:* Robust retry semantics, hard/soft task timeout enforcement, and memory reclamation.
  - *Implications:* Task payloads must be strictly JSON-serialized; Python pickle is prohibited for security.

---

### ADR-004: Storage Provider Abstraction & Evidence Immutability

- **Date:** 2026-10
- **Status:** Accepted
- **Decision & Context:**
  Introduce an abstract `StorageProvider` interface (`put_stream`, `get_stream`, `get_local_path_readonly`). Initial deployment uses `LocalFilesystemStorageProvider` applying POSIX `chmod 0400` (read-only) upon ingestion.
- **Reasoning:**
  Forensic laboratories often operate in air-gapped environments without cloud access, while enterprise deployments require cloud object stores with S3 Object Lock (WORM). The abstraction decouples domain services from physical filesystem paths and protects against path traversal.
- **Alternatives Considered:**
  1. *Direct Filesystem Calls (`open()`):* Rejected due to tight platform coupling, security vulnerabilities, and inability to support cloud storage.
  2. *S3-Only Architecture:* Rejected because air-gapped forensic labs cannot access public cloud endpoints.
- **Consequences:**
  - *Positive:* Complete storage portability between local air-gapped workstations and cloud environments.
  - *Implications:* All file interactions must pass through the storage provider abstraction rather than raw OS paths.

---

### ADR-005: Hybrid Forensic Tooling Strategy (Subprocess vs Native Python)

- **Date:** 2026-10
- **Status:** Accepted
- **Decision & Context:**
  Use an isolated subprocess wrapper for Phil Harvey's ExifTool and FFmpeg/FFprobe, while running ELA (Pillow/NumPy), temporal analysis (OpenCV), and audio DSP (librosa/SciPy) as native Python functions in workers.
- **Reasoning:**
  ExifTool is the gold standard supporting 25,000+ proprietary camera MakerNotes and container atoms that no Python library covers. However, running math and image algorithms as subprocesses would incur severe cold-start import overhead.
- **Alternatives Considered:**
  1. *Native Python EXIF parsers (`piexif`, `exifread`):* Rejected because they support only a fraction of ExifTool's tag coverage.
  2. *Subprocesses for all analysis tools:* Rejected due to severe cold-start overhead when repeatedly spawning Python runtimes for matrix math.
- **Consequences:**
  - *Positive:* Maximum metadata coverage with peak computational efficiency.
  - *Implications:* Deployment containers must bundle Perl (for ExifTool) and FFmpeg system packages alongside Python dependencies.

---

### ADR-006: Programmatic PDF Report Engine (ReportLab vs Headless Chromium)

- **Date:** 2026-10
- **Status:** Accepted
- **Decision & Context:**
  Use ReportLab with the Platypus architecture for programmatic PDF report compilation.
- **Reasoning:**
  Courtroom evidence reports require byte-exact deterministic rendering, precise page-budget control, vector canvas drawing, and embedded hash seals. Headless browsers (Puppeteer/Playwright) consume 500MB+ RAM per instance, introduce non-deterministic pagination, and introduce significant attack surfaces.
- **Alternatives Considered:**
  1. *Headless Chromium / Puppeteer / WeasyPrint:* High memory consumption, non-deterministic page breaks, and severe security sandbox risks.
  2. *LaTeX:* Superb typesetting, but requires multi-gigabyte TeX distributions and is complex to integrate dynamically with image artifacts.
- **Consequences:**
  - *Positive:* Extremely lightweight, deterministic page budget calculations, and zero headless browser attack surface.
  - *Implications:* Document layouts must be declared using ReportLab's Python Platypus primitives rather than HTML/CSS.

---

### ADR-007: Cryptographic Hash Chaining & DB Triggers for Audit Immutability

- **Date:** 2026-10
- **Status:** Accepted
- **Decision & Context:**
  Enforce chain-of-custody immutability at the database engine level via SQL triggers on `audit_events` and critical hash columns of `evidence_items`, combined with cryptographic SHA-256 hash chaining of audit events.
- **Reasoning:**
  To satisfy Federal Rules of Evidence (FRE 901/902), the system must prove in court that evidence records and audit entries were not tampered with, even by a database administrator. Application-level checks alone are insufficient because direct SQL queries could modify records.
- **Alternatives Considered:**
  1. *External Blockchain / Ledger Service:* Expensive, vendor-locked, and incompatible with air-gapped forensic labs.
  2. *Application-Only Read-Only Checks:* Insufficient to withstand courtroom scrutiny against database-level manipulation.
- **Consequences:**
  - *Positive:* Legally defensible, mathematically verifiable chain of custody meeting courtroom self-authentication standards.
  - *Implications:* Audit records can never be updated or deleted in the database without raising an engine-level error.

---

### ADR-008: Dual-Engine SQLite/PostgreSQL Database Anti-Tamper Triggers

- **Date:** 2026-10-23
- **Status:** Accepted
- **Decision & Context:**
  Implement anti-tampering triggers for both PostgreSQL (PL/pgSQL functions) and SQLite (`BEFORE UPDATE` / `BEFORE DELETE` triggers with `RAISE(ABORT, ...)`).
- **Reasoning:**
  Automated testing must run rapidly in memory (`sqlite+aiosqlite:///:memory:`) in CI and local developer workstations without requiring a live external PostgreSQL instance. Enforcing the triggers in SQLite ensures that integration tests verify real trigger execution and anti-tamper behavior during test execution.
- **Alternatives Considered:**
  1. *PostgreSQL-Only Triggers:* Would require spinning up a Dockerized PostgreSQL container for every unit test execution, slowing down test cycles and failing in environments lacking Docker.
  2. *Mocking Database Triggers in Tests:* Rejected because testing actual database engine rejection is critical for forensic integrity assurance.
- **Consequences:**
  - *Positive:* Developers can run fast, isolated in-memory test suites that verify genuine database-level anti-tampering enforcement.
  - *Implications:* Trigger definitions must be maintained in both PL/pgSQL and SQLite SQL syntax within `app/db/triggers.py` and `alembic/versions/0001_initial_schema.py`.
