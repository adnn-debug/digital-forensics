# PS-05 Digital Evidence Authenticity & Integrity Verification Platform
## Repository Tree & Codebase Layout

**Document Version:** 1.0.0  
**Status:** Approved Layout Specification  

---

```
digital-forensics/
├── .env.example                               # Canonical template for environment variables
├── .gitignore                                 # Git ignore patterns for Python, Node, data vaults
├── README.md                                  # Platform overview, rapid setup guide, and legal notices
├── docker-compose.yml                         # Multi-container orchestration (API, Worker, UI, DB, Redis)
│
├── docs/                                      # System Architecture & Engineering Documentation
│   ├── ARCHITECTURE.md                        # High-level architecture, subsystem roles & components
│   ├── DATA_FLOW.md                           # Ingestion, analysis, report & audit sequence flows
│   ├── SECURITY_THREAT_MODEL.md               # STRIDE threat model & parser hardening specs
│   ├── FORENSIC_LIMITATIONS.md                # Methodological limitations & legal caveats
│   ├── ADR.md                                 # Architecture Decision Records (ADR-001 to ADR-007)
│   ├── REPO_TREE.md                           # This repository tree specification
│   └── PLAN.md                                # Phased implementation plan with acceptance tests
│
├── docker/                                    # Container Build Definitions & Hardening Configs
│   ├── backend/
│   │   ├── Dockerfile                         # Python 3.11 base + ExifTool + FFmpeg + dependencies
│   │   └── entrypoint.sh                      # Database migration runner & FastAPI bootstrapper
│   ├── worker/
│   │   ├── Dockerfile                         # Dedicated Celery worker image with non-root security
│   │   └── entrypoint.sh                      # Celery worker process startup script
│   └── frontend/
│       ├── Dockerfile                         # Multi-stage Next.js production build
│       └── nginx.conf                         # Reverse proxy configuration (if deploying standalone)
│
├── storage/                                   # Local Private Storage Vault Root (Mounted via Volume)
│   ├── quarantine/                            # Ephemeral upload staging before hash verification
│   ├── vault/                                 # Permanent, immutable evidence files (chmod 0400)
│   ├── artifacts/                             # Derivative forensic outputs (ELA heatmaps, plots, frames)
│   └── reports/                               # Compiled courtroom PDF reports
│
├── backend/                                   # Backend Modular Monolith Subsystem
│   ├── pyproject.toml                         # Poetry / Pip build definitions & pinned dependencies
│   ├── requirements.txt                       # Production locked requirements
│   ├── requirements-dev.txt                   # Linting, typing (mypy, ruff), and testing tools
│   ├── alembic.ini                            # Database migration configuration
│   │
│   ├── alembic/                               # Database Schema Version Control
│   │   ├── env.py                             # Async migration environment script
│   │   ├── script.py.mako                     # Migration template
│   │   └── versions/                          # Migration revision files (0001_initial_schema.py, etc.)
│   │
│   ├── app/                                   # Core Application Package
│   │   ├── __init__.py
│   │   ├── main.py                            # ASGI application entrypoint & middleware configuration
│   │   ├── config.py                          # Pydantic Settings (Environment variables, secret keys)
│   │   │
│   │   ├── api/                               # Layer 1: HTTP Presentation Layer (FastAPI Routers)
│   │   │   ├── __init__.py
│   │   │   ├── deps.py                        # Dependency injection (DB session, current user, storage)
│   │   │   ├── v1/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── router.py                  # Master API v1 router aggregator
│   │   │   │   ├── auth.py                    # Authentication endpoints (login, token refresh)
│   │   │   │   ├── cases.py                   # Case management endpoints (create, list, get, update)
│   │   │   │   ├── evidence.py                # Evidence ingestion, streaming download, hash verification
│   │   │   │   ├── analyses.py                # Forensic job dispatching, status polling, result retrieval
│   │   │   │   ├── artifacts.py               # Secure delivery of derivative forensic artifacts
│   │   │   │   ├── reports.py                 # Courtroom PDF report generation & download
│   │   │   │   └── audit.py                   # Chain-of-custody & immutable audit log query endpoints
│   │   │
│   │   ├── schemas/                           # Layer 1b: Pydantic DTOs & Request/Response Models
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                        # Token, LoginRequest schemas
│   │   │   ├── case.py                        # CaseCreate, CaseResponse schemas
│   │   │   ├── evidence.py                    # EvidenceUploadResponse, EvidenceDetail schemas
│   │   │   ├── forensic.py                    # AnalysisRequest, ELAResponse, SpectrogramResponse schemas
│   │   │   ├── report.py                      # ReportRequest, ReportResponse schemas
│   │   │   └── audit.py                       # AuditEventResponse, ChainVerification schemas
│   │   │
│   │   ├── services/                          # Layer 2: Business Logic & Orchestration
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py                # User credentials, JWT generation, password hashing
│   │   │   ├── case_service.py                # Case lifecycle, access permissions, status workflows
│   │   │   ├── evidence_service.py            # Stream ingestion, dual hashing, storage coordinator
│   │   │   ├── verification_service.py        # Cryptographic hash integrity re-verification engine
│   │   │   ├── analysis_orchestrator.py       # Asynchronous task dispatching & validation
│   │   │   ├── audit_service.py               # Tamper-evident audit logging & hash chain validation
│   │   │   └── report_service.py              # Case data aggregator & ReportLab compilation invoker
│   │   │
│   │   ├── domain/                            # Layer 3: Domain Entities, Enums & Exceptions
│   │   │   ├── __init__.py
│   │   │   ├── enums.py                       # MediaType, AnalysisType, CaseStatus, AuditEventType
│   │   │   └── exceptions.py                  # Domain-specific errors (IntegrityTamperException, etc.)
│   │   │
│   │   ├── db/                                # Layer 4: Persistence Infrastructure (SQLAlchemy)
│   │   │   ├── __init__.py
│   │   │   ├── session.py                     # Async database engine & scoped session factory
│   │   │   ├── base.py                        # Declarative Base metadata
│   │   │   └── models/                        # ORM Entity Models
│   │   │       ├── __init__.py
│   │   │       ├── user.py                    # User model
│   │   │       ├── case.py                    # Case model
│   │   │       ├── evidence.py                # EvidenceItem & HashVerification models
│   │   │       ├── metadata.py                # MetadataExtract model (JSONB storage)
│   │   │       ├── analysis.py                # ForensicAnalysis & AnalysisArtifact models
│   │   │       ├── audit.py                   # AuditEvent model (with previous_hash chain)
│   │   │       └── report.py                  # Report model
│   │   │
│   │   ├── storage/                           # Layer 5: Storage Abstraction Layer
│   │   │   ├── __init__.py
│   │   │   ├── base.py                        # Abstract Base Class: StorageProvider
│   │   │   ├── local.py                       # LocalFilesystemStorageProvider (with chmod 0400)
│   │   │   └── s3.py                          # S3CompatibleStorageProvider (MinIO / AWS S3 WORM adapter)
│   │   │
│   │   ├── forensics/                         # Layer 6: Isolated Forensic Engines
│   │   │   ├── __init__.py
│   │   │   ├── base.py                        # Abstract Base Class: BaseForensicEngine
│   │   │   ├── metadata_extractor.py          # ExifTool & FFprobe sandboxed subprocess runners
│   │   │   ├── image_ela.py                   # Pillow & NumPy Error Level Analysis (ELA) engine
│   │   │   ├── video_analyzer.py              # FFmpeg & OpenCV keyframe extractor and temporal analyzer
│   │   │   └── audio_spectrogram.py           # librosa & SciPy DSP audio spectrogram/waveform engine
│   │   │
│   │   ├── reports/                           # Layer 7: Courtroom PDF Generation (ReportLab)
│   │   │   ├── __init__.py
│   │   │   ├── generator.py                   # ReportLab Platypus document assembler
│   │   │   ├── templates.py                   # Legal document layout styles, margins, headers/footers
│   │   │   ├── components.py                  # Reusable PDF elements (hash seals, tables, visual figures)
│   │   │   └── seals.py                       # Cryptographic hash badges and verification QR generator
│   │   │
│   │   └── workers/                           # Layer 8: Asynchronous Worker Tasks (Celery)
│   │       ├── __init__.py
│   │       ├── celery_app.py                  # Celery application configuration & Redis broker bindings
│   │       └── tasks.py                       # Background task definitions (run_analysis, verify_hashes)
│   │
│   └── tests/                                 # Automated Test Suite (Pytest)
│       ├── conftest.py                        # Test fixtures (async DB session, mock storage, client)
│       ├── test_media/                        # Sample forensic media files (test.jpg, test.mp3, test.mp4)
│       ├── unit/                              # Isolated component tests
│       │   ├── test_hashing.py                # Streaming SHA-256 / SHA-1 / MD5 digest verification
│       │   ├── test_ela.py                    # ELA computation and heatmap generation tests
│       │   ├── test_audio_dsp.py              # Spectrogram and STFT mathematical correctness
│       │   ├── test_video_frames.py           # Frame extraction and keyframe slicing tests
│       │   ├── test_metadata_sanitization.py  # ExifTool subprocess argument escaping
│       │   └── test_report_builder.py         # ReportLab PDF creation and hash sealing tests
│       └── integration/                       # End-to-end API and workflow tests
│           ├── test_evidence_ingestion.py     # Upload stream -> hash -> vault -> DB commit
│           ├── test_tamper_detection.py       # Simulated bit-flip detection test
│           ├── test_audit_immutability.py     # Test PostgreSQL triggers blocking updates
│           └── test_worker_pipeline.py        # Asynchronous job dispatch and artifact generation
│
└── frontend/                                  # Next.js 14/15 Frontend Web Application
    ├── package.json                           # Next.js, React, Tailwind CSS, Lucide icons dependencies
    ├── tsconfig.json                          # TypeScript strict configuration
    ├── tailwind.config.ts                     # Forensic high-contrast / dark theme design tokens
    ├── postcss.config.js                      # PostCSS pipeline
    ├── next.config.mjs                        # Next.js configuration (API proxying, image optimization)
    │
    ├── public/                                # Static web assets (logos, law enforcement seals, icons)
    │
    └── src/
        ├── app/                               # Next.js App Router (File-based routing)
        │   ├── layout.tsx                     # Root layout with navigation shell and theme provider
        │   ├── page.tsx                       # Landing / System Overview / Authentication redirect
        │   ├── login/
        │   │   └── page.tsx                   # Secure login view
        │   ├── cases/
        │   │   ├── page.tsx                   # Case management index (search, filter, create case)
        │   │   └── [caseId]/
        │   │       ├── page.tsx               # Case detail view (evidence inventory, timeline, status)
        │   │       ├── upload/
        │   │       │   └── page.tsx           # Streaming evidence upload & hash verification view
        │   │       └── reports/
        │   │           └── page.tsx           # Case reports generator and download gallery
        │   └── evidence/
        │       └── [evidenceId]/
        │           ├── page.tsx               # Evidence detail & chain-of-custody ledger view
        │           └── analyze/
        │               ├── ela/page.tsx       # Interactive ELA visualizer (side-by-side zoom & heatmap)
        │               ├── video/page.tsx     # Keyframe carousel & temporal frame inspection
        │               └── audio/page.tsx     # Synchronized audio player & Mel-spectrogram viewer
        │
        ├── components/                        # Reusable React UI Components
        │   ├── ui/                            # Base primitives (Button, Modal, Card, Badge, Alert, Tabs)
        │   ├── layout/                        # AppHeader, Sidebar, NavigationBreadcrumb
        │   ├── cases/                         # CaseCard, CaseForm, CaseStatusBadge
        │   ├── evidence/                      # EvidenceUploader, HashVerificationBadge, CustodyTimeline
        │   ├── forensics/                     # ELAViewer, SpectrogramViewer, KeyframeCarousel, MetadataTable
        │   └── reports/                       # ReportPreviewModal, CryptographicSealCard
        │
        ├── hooks/                             # Custom React Hooks
        │   ├── useEvidenceUpload.ts           # Upload progress tracking and hash confirmation
        │   ├── useForensicJob.ts              # Asynchronous job status polling & completion notifications
        │   └── useAudioVisualizer.ts          # Synchronized audio playback with spectrogram tracking
        │
        ├── lib/                               # Client-side Utilities & SDK Client
        │   ├── api.ts                         # Typed Axios/Fetch API client for FastAPI backend
        │   ├── formatters.ts                  # Byte size, date/timestamp (ISO-8601), and hash formatters
        │   └── constants.ts                   # Analysis types, status enums, route definitions
        │
        └── types/                             # TypeScript Interface Declarations
            ├── api.ts                         # Generic API response and pagination models
            ├── case.ts                        # Case, CaseStatus, Investigator types
            ├── evidence.ts                    # EvidenceItem, HashVerification, MediaType types
            ├── forensic.ts                    # ELAResult, SpectrogramResult, VideoFramesResult types
            └── audit.ts                       # AuditEvent, ChainOfCustodyRecord types
```
