# PS-05 Digital Evidence Authenticity & Integrity Verification Platform
## Data Flow Specification

**Document Version:** 1.0.0  
**Status:** Approved Engineering Specification  
**Subject:** End-to-End Ingestion, Verification, Forensic Analysis, and Report Lifecycles

---

### 1. Ingestion & Cryptographic Baseline Pipeline

The ingestion pipeline must guarantee that evidence files cannot enter the platform without an immutable cryptographic fingerprint established at the raw network stream boundary.

```mermaid
sequenceDiagram
    autonumber
    actor Examiner as Forensic Examiner
    participant UI as Next.js Web Client
    participant API as FastAPI Ingestion Router
    participant Svc as EvidenceService
    participant HashEngine as Streaming Hash Processor
    participant Vault as Storage Vault (Local / Object)
    participant DB as PostgreSQL Database
    participant Audit as Audit Logging Service

    Examiner->>UI: Select Case & Upload Evidence (Image / Audio / Video)
    UI->>API: Multipart POST /api/v1/cases/{case_id}/evidence
    API->>Svc: Hand off multipart stream & file metadata
    
    rect rgb(240, 248, 255)
        note over Svc,HashEngine: Dual-Hashing on Wire
        Svc->>HashEngine: Pipe stream simultaneously to SHA-256, SHA-1, and MD5
        Svc->>Vault: Write stream to Quarantined Staging Path
        HashEngine-->>Svc: Finalize Digests (SHA-256, SHA-1, MD5) & Byte Count
    end

    Svc->>Vault: Move quarantined file to Permanent Immutable Path (0400 read-only)
    
    rect rgb(245, 255, 245)
        note over Svc,DB: Transactional State Commitment
        Svc->>DB: INSERT into evidence_items (case_id, hashes, storage_path, mime_type)
        Svc->>DB: INSERT into hash_verifications (initial baseline record)
        Svc->>Audit: Record AUDIT_EVENT (EVENT_EVIDENCE_INGESTED, user_id, hash, client_ip)
        Audit->>DB: INSERT into audit_events (with previous event HMAC chain)
    end

    Svc-->>API: EvidenceRecord DTO
    API-->>UI: 201 Created (Evidence ID, SHA-256 Digest, Ingestion Timestamp)
    UI-->>Examiner: Display Evidence Ingested & Verified Sound
```

#### Step-by-Step Ingestion Mechanics:
1. **Network Boundary Stream Interception:** The file stream is consumed chunk-by-chunk (e.g., 64 KB chunks). It is never loaded into RAM as a monolithic byte array.
2. **Concurrent Streaming Digests:** A dedicated multi-hasher updates Python `hashlib.sha256()`, `hashlib.sha1()`, and `hashlib.md5()` contexts simultaneously while streaming raw chunks directly to the storage driver.
3. **Quarantine Staging:** During transfer, the file resides in an isolated quarantine directory (`/storage/quarantine/{uuid}.tmp`). If the connection drops or the client aborts, the incomplete file is immediately scrubbed without touching the database.
4. **Locking & Permissions:** Once the stream closes and hashes match, the storage adapter moves the file into `/storage/vault/{case_id}/{evidence_id}/{filename}` and removes write permissions (`chmod 0400` in Linux/POSIX).
5. **Chain of Custody Initialization:** The first chain-of-custody entry is immutably committed with the examiner ID, timestamp, source IP address, and computed hash.

---

### 2. Forensic Analysis Pipeline (Asynchronous Worker Execution)

Once evidence is stored, examiners initiate targeted forensic analysis routines. Because these operations are computationally intensive, they are delegated via Redis to the Celery worker fleet.

```mermaid
sequenceDiagram
    autonumber
    actor Examiner as Forensic Examiner
    participant UI as Next.js Web Client
    participant API as FastAPI Analysis Router
    participant Queue as Redis Message Broker
    participant Worker as Forensic Worker (Celery)
    participant Forensics as Forensic Engines (ExifTool / OpenCV / librosa)
    participant Vault as Storage Vault
    participant DB as PostgreSQL Database
    participant Audit as Audit Logging Service

    Examiner->>UI: Select Analysis Routine (e.g. ELA / Spectrogram / Frames)
    UI->>API: POST /api/v1/evidence/{evidence_id}/analyses {type, params}
    API->>DB: INSERT into forensic_analyses (status="PENDING")
    API->>Audit: Log AUDIT_EVENT (ANALYSIS_INITIATED)
    API->>Queue: Push Task dispatch_forensic_analysis(analysis_id)
    API-->>UI: 202 Accepted (Analysis ID, Status: PENDING)

    rect rgb(255, 250, 240)
        note over Queue,Worker: Background Job Execution
        Queue->>Worker: Consume Task (analysis_id)
        Worker->>DB: UPDATE forensic_analyses status="IN_PROGRESS"
        Worker->>Vault: Acquire Read-Only File Handle
        
        note over Worker,Forensics: Integrity Pre-Check
        Worker->>Worker: Recalculate SHA-256 against DB baseline
        alt Hash Mismatch (Evidence Tampered!)
            Worker->>DB: UPDATE status="FAILED" (Integrity Violation)
            Worker->>Audit: Log CRITICAL_SECURITY_ALERT (INTEGRITY_TAMPER_DETECTED)
        else Hash Verified
            Worker->>Forensics: Execute Forensic Engine with timeout & sandboxing
            Forensics-->>Worker: Yield Summary Metrics + Output Artifacts
            Worker->>Vault: Store derivative artifacts (heatmaps / plots / keyframes)
            Worker->>DB: INSERT analysis_artifacts records
            Worker->>DB: UPDATE forensic_analyses (status="COMPLETED", summary_results)
            Worker->>Audit: Log AUDIT_EVENT (ANALYSIS_COMPLETED)
        end
    end

    UI->>API: Poll GET /api/v1/analyses/{analysis_id} (or SSE/WebSocket)
    API->>DB: Query status
    DB-->>API: Return Analysis Details & Artifact URLs
    API-->>UI: Return 200 OK (Analysis Results)
    UI-->>Examiner: Render Visualizations (Interactive Spectrogram / ELA Heatmap / Frames)
```

---

### 3. Media-Specific Modality Pipelines

#### 3.1 Image Forensic Pipeline: Metadata & Error Level Analysis (ELA)

```mermaid
flowchart TD
    ImgIn["Raw Image Evidence (.jpg, .jpeg, .png, .tiff)"] --> HashCheck{"SHA-256 Integrity Verified?"}
    HashCheck -- No --> Abort["Halt & Flag Tamper Alert"]
    HashCheck -- Yes --> BranchMeta["Fork: Parallel Processing"]

    subgraph MetadataTrack ["Track A: Metadata Deep Extraction"]
        BranchMeta --> ExifSub["ExifTool CLI Subprocess (-json -G -a -u)"]
        ExifSub --> CleanJSON["Sanitize & Structure EXIF/IPTC/XMP"]
        CleanJSON --> SerialMatch["Flag Camera Make/Model/Serial Anomalies"]
        CleanJSON --> TimeDiscrepancy["Cross-check EXIF Time vs File Timestamp"]
    end

    subgraph ELATrack ["Track B: Error Level Analysis Engine"]
        BranchMeta --> OpenPillow["Load Original Image (Pillow RGB)"]
        OpenPillow --> SaveTemp["Re-save in memory as JPEG (Quality 95 & 75)"]
        SaveTemp --> DiffMatrix["Compute Pixel Difference Matrix: |Orig - Resaved|"]
        DiffMatrix --> ScaleExtrema["Auto-scale & Stretch Difference Extrema"]
        ScaleExtrema --> GenHeatmap["Apply Colormap (Heatmap Artifact PNG)"]
        ScaleExtrema --> Metrics["Compute Mean & StdDev Error per Block"]
    end

    SerialMatch --> MergeResults["Synthesize Results Model"]
    TimeDiscrepancy --> MergeResults
    GenHeatmap --> StoreArtifact["Save ELA Artifact to Vault"]
    Metrics --> MergeResults
    StoreArtifact --> DBCommit["Commit to DB & Audit Log"]
    MergeResults --> DBCommit
```

#### 3.2 Video Forensic Pipeline: Container Probing, Keyframe Indexing & Temporal Slicing

```mermaid
flowchart TD
    VidIn["Raw Video Evidence (.mp4, .mov, .avi, .mkv)"] --> HashCheck{"SHA-256 Integrity Verified?"}
    HashCheck -- No --> Abort["Halt & Flag Tamper Alert"]
    HashCheck -- Yes --> FFprobe["FFprobe Subprocess (-show_streams -show_format)"]

    FFprobe --> StreamProfile["Profile Video/Audio Codecs, Bitrate, SAR/DAR, Variable Frame Rate (VFR)"]
    StreamProfile --> FFmpegKeyframes["FFmpeg I-Frame Extraction: -vf select='eq(pict_type,PICT_TYPE_I)'"]
    FFmpegKeyframes --> KeyframeDir["Extract Keyframe JPGs to Sandbox"]

    KeyframeDir --> OpenCVLoop["OpenCV Sequence Loop"]
    OpenCVLoop --> FrameHash["Compute Per-Frame pHash & dHash"]
    OpenCVLoop --> SceneDetect["Detect Scene Cuts & Frame Jumps via Histogram Diff"]
    OpenCVLoop --> SampleIntervals["Extract Uniform Temporal Samples (1 frame/sec)"]

    SampleIntervals --> SaveThumbnails["Store Keyframe Carousel Artifacts"]
    FrameHash --> AnomalyScan["Identify Temporal Discontinuities or Duplicate Drops"]
    SceneDetect --> AnomalyScan
    
    SaveThumbnails --> FinalizeVideo["Save Analysis Artifacts & JSON Timeline"]
    AnomalyScan --> FinalizeVideo
```

#### 3.3 Audio Forensic Pipeline: Codec Decoding, Waveform Envelope & Spectrogram Analysis

```mermaid
flowchart TD
    AudIn["Raw Audio Evidence (.wav, .mp3, .m4a, .aac, .flac)"] --> HashCheck{"SHA-256 Integrity Verified?"}
    HashCheck -- No --> Abort["Halt & Flag Tamper Alert"]
    HashCheck -- Yes --> FFmpegDecode["Decode Container via FFmpeg to 32-bit Float PCM"]

    FFmpegDecode --> LibrosaLoad["Load Normalized PCM Array (librosa / SoundFile)"]
    
    subgraph TimeDomain ["Track 1: Time Domain Analysis"]
        LibrosaLoad --> WaveEnvelope["Compute Root Mean Square (RMS) Energy"]
        WaveEnvelope --> ZeroCrossing["Zero Crossing Rate (ZCR) Calculation"]
        ZeroCrossing --> WaveformPNG["Generate High-Resolution Waveform Visualization (PNG)"]
    end

    subgraph FrequencyDomain ["Track 2: Spectral & Frequency Domain Analysis"]
        LibrosaLoad --> STFT["Short-Time Fourier Transform (STFT) with Hann Window"]
        STFT --> MelScale["Compute Mel-Frequency Spectrogram (dB Scale)"]
        MelScale --> CutoffDetect["High-Frequency Cutoff Detection (Signs of MP3 transcoding)"]
        MelScale --> ENFAnalysis["Electric Network Frequency (ENF) Scan (50Hz / 60Hz hum continuity)"]
        MelScale --> SpectrogramPNG["Render Color-graded Spectrogram (Matplotlib/Pillow -> PNG)"]
    end

    WaveformPNG --> VaultSave["Save Derivative Images in Vault"]
    SpectrogramPNG --> VaultSave
    CutoffDetect --> AudioSummary["Synthesize Acoustic Metrics JSON"]
    ENFAnalysis --> AudioSummary
    VaultSave --> FinalAudioCommit["Commit Analysis & Artifact Records"]
    AudioSummary --> FinalAudioCommit
```

---

### 4. Courtroom PDF Report Compilation Data Flow

Generating a forensic examination report requires aggregating the complete evidentiary record, verifying that no data has changed, and compiling a tamper-evident document.

```mermaid
sequenceDiagram
    autonumber
    actor Examiner as Forensic Examiner
    participant UI as Next.js Web Client
    participant API as FastAPI Reports Router
    participant RptSvc as ReportService
    participant DB as PostgreSQL Database
    participant Vault as Storage Vault
    participant PDFEngine as ReportLab PDF Engine
    participant Audit as Audit Logging Service

    Examiner->>UI: Request Export Courtroom Forensic Report
    UI->>API: POST /api/v1/cases/{case_id}/reports/generate {title, evidence_ids, notes}
    API->>RptSvc: Trigger Report Assembly
    
    rect rgb(255, 250, 245)
        note over RptSvc,DB: Aggregation & Integrity Verification
        RptSvc->>DB: Fetch Case Details, Examiner Credentials
        RptSvc->>DB: Fetch Evidence Records & Verification Histories
        RptSvc->>DB: Fetch Forensic Analyses & Artifact Paths
        RptSvc->>DB: Fetch Immutable Audit Trail Chronology
        
        loop For Each Selected Evidence Item
            RptSvc->>RptSvc: Recalculate SHA-256 on live vault file
            RptSvc->>RptSvc: Compare against Ingestion Hash Baseline
        end
    end

    rect rgb(240, 248, 255)
        note over RptSvc,PDFEngine: ReportLab Compilation
        RptSvc->>Vault: Fetch Artifact Bitmaps (ELA Heatmaps, Spectrograms, Keyframes)
        RptSvc->>PDFEngine: Pass Aggregated Evidentiary Data Context
        PDFEngine->>PDFEngine: Build Flowables (Case Header, Chain of Custody Table, Visual Figures)
        PDFEngine->>PDFEngine: Generate Cryptographic Verification QR Code & Summary Hash
        PDFEngine->>PDFEngine: Render Two-Pass Document (Page X of Y, Running Headers)
        PDFEngine-->>RptSvc: Complete PDF Byte Stream
    end

    RptSvc->>RptSvc: Calculate SHA-256 Digest of Generated PDF
    RptSvc->>Vault: Save PDF to Reports Vault (/reports/{report_id}.pdf)
    RptSvc->>DB: INSERT into reports (report_number, file_hash_sha256, storage_path)
    RptSvc->>Audit: Record AUDIT_EVENT (REPORT_GENERATED, report_hash)

    RptSvc-->>API: ReportMetadata DTO
    API-->>UI: 201 Created (Report ID, Download URL, Document SHA-256)
    UI-->>Examiner: Present Download Button & Cryptographic Verification Seal
```

---

### 5. Chain-of-Custody & Audit Trail Integrity Flow

All security-sensitive operations generate immutable audit events. To prevent post-facto tampering with the database, events are secured using a cryptographic hash chain.

```mermaid
flowchart LR
    EventN1["Audit Event N-1\nHash: e3b0c44298fc..."] --> EventN["Audit Event N\n- ID: UUID\n- Event: EVIDENCE_ANALYSIS_EXECUTED\n- User: Examiner Jane Doe\n- Timestamp: 2026-10-23T19:50:00Z\n- PrevHash: e3b0c44298fc...\n- Payload: {evidence_id, tool_params}"]
    
    EventN --> HashCalc["SHA-256(PrevHash + EventID + Timestamp + UserID + Payload)"]
    HashCalc --> EventNHash["Event N Hash: 8f43a2b109..."]
    
    EventNHash --> EventNPlus1["Audit Event N+1\nPrevHash: 8f43a2b109..."]
```

If an adversary alters a row in the `audit_events` table (for instance, changing an examiner ID or backdating an ingestion timestamp), the cryptographic hash chain breaks immediately. The platform's automated daily verification routine flags the tampering and identifies the exact corrupted block.
