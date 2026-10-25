# PS-05 Digital Evidence Authenticity & Integrity Verification Platform
## Security Threat Model & Hardening Outline

**Document Version:** 1.0.0  
**Classification:** Critical Security & Chain-of-Custody Defense  
**Methodology:** STRIDE Threat Modeling & NIST SP 800-86 Guide to Integrating Forensic Techniques into Incident Response

---

### 1. Threat Modeling Overview

Digital forensics platforms are high-value targets. Attackers may attempt to:
1. **Tamper with Evidence:** Modify evidence items to subvert criminal prosecutions or civil litigation.
2. **Exploit Forensic Parsers:** Upload weaponized media files designed to trigger Remote Code Execution (RCE) via vulnerabilities in complex C/Perl parsers (such as ExifTool, FFmpeg, OpenCV, or libsndfile).
3. **Corrupt Chain of Custody:** Alter audit logs or timestamps to discredit the admissibility of forensic reports in court.
4. **Denial of Service (DoS):** Exhaust memory, disk, or CPU resources by submitting decompression bombs or malformed media streams.

---

### 2. STRIDE Threat Analysis Matrix

| Threat Category | Primary Target | Potential Vector | Platform Mitigation Architecture |
| :--- | :--- | :--- | :--- |
| **Spoofing** | User Identity & API | Stolen credentials, forged session tokens | JWT tokens with short TTLs, bcrypt password hashing, HTTP-only secure samesite cookies, multi-factor authentication (MFA) capability. |
| **Tampering** | Evidence Files & Audit Logs | Direct file manipulation on disk, DB row modification | Stream-level SHA-256 calculation at ingestion; POSIX `chmod 0400` write-prohibition; PostgreSQL DB triggers forbidding `UPDATE` and `DELETE` on audit & evidence records; SHA-256 HMAC hash chaining across audit rows. |
| **Repudiation** | Actions of Examiners | Examiner denies viewing, modifying, or exporting reports | Unconditional, append-only audit logging recording User ID, client IP address, User-Agent, exact action payload, and timestamp for every API invocation. |
| **Information Disclosure** | Evidence Storage & Reports | Unauthorized cross-case data access, path traversal | UUID-based content-addressable storage paths; zero direct public web access to storage root; pre-authenticated streaming endpoints enforcing case membership RBAC; sanitized error outputs concealing server internals. |
| **Denial of Service** | Forensic Workers & API | Pixel flood bombs, recursive container atoms, infinite loop media | Hard worker memory caps (`--max-tasks-per-child=50`, memory limits via Docker cgroups); strict file size limits (5 GB max); processing timeouts (e.g. 60s for images, 900s for video); Pillow `Image.MAX_IMAGE_PIXELS` safety bounds. |
| **Elevation of Privilege** | Backend Server & Worker Host | RCE via parser vulnerabilities (ExifTool, FFmpeg) | Worker processes run as non-root unprivileged users (`forensic:forensic`, UID 10001); container filesystem mounted read-only (`read_only: true` except isolated `/tmp`); all subprocess calls use non-shell explicit argument arrays (`subprocess.run(["exiftool", ...], shell=False)`). |

---

### 3. File Upload & Parser Vulnerability Hardening

#### 3.1 Exploits in Media Parsing Engines (e.g. ExifTool, FFmpeg)
*Historical Precedent:* CVE-2021-22204 (ExifTool DjVu parsing arbitrary code execution), CVE-2020-0499 (FFmpeg FLAC parsing out-of-bounds read/write).

**Architectural Defenses:**
1. **Zero Shell Invocations:** Under no circumstances are commands concatenated as strings. Python `subprocess.run()` is strictly invoked with `shell=False` and explicit argument lists:
   ```python
   # SECURE IMPLEMENTATION PATTERN:
   cmd = ["exiftool", "-json", "-G", "-charset", "filename=UTF8", "--", str(safe_file_path)]
   result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, shell=False)
   ```
2. **Double-Dash Argument Terminator (`--`):** Invocations include `--` prior to the file argument to prevent malicious filenames (e.g., `-config/etc/passwd`) from being interpreted as CLI flags.
3. **Execution Sandboxing:** Subprocesses run inside an unprivileged Docker container with drop capabilities:
   ```yaml
   security_opt:
     - no-new-privileges:true
   cap_drop:
     - ALL
   ```
4. **Isolated Ephemeral Working Directories:** Derivative processing occurs in short-lived scratch directories (`/tmp/forensics/{uuid}/`) that are automatically wiped in Python `finally:` blocks.

#### 3.2 Polyglot Files & MIME-Type Spoofing
Attackers often disguise executable scripts or PHP shells by prepending valid JPEG or MP4 headers (e.g., `GIF89a` polyglots).

**Architectural Defenses:**
- Content validation is never based on the user-supplied HTTP `Content-Type` header or file extension.
- Magic byte inspection (via `python-magic` / `libmagic`) is verified against the binary payload.
- For image evidence, Pillow opens and verifies the internal image matrix (`Image.verify()`). If decoding fails, the file is rejected immediately.

#### 3.3 Decompression Bombs & Pixel Floods
Images with small compressed disk sizes (e.g., 2 MB) can decompress into billions of pixels, consuming tens of gigabytes of RAM.

**Architectural Defenses:**
- Strict configuration of Pillow decompression limit:
  ```python
  from PIL import Image
  Image.MAX_IMAGE_PIXELS = 100_000_000  # Enforce hard 100 MP limit (approx ~400MB uncompressed in RAM)
  ```
- Subprocess timeout limits (e.g., 30 seconds for ExifTool, 300 seconds for FFmpeg). If a process stalls or loops indefinitely, the parent process terminates it via `SIGKILL`.

---

### 4. Storage Security & Path Traversal Prevention

1. **Storage Separation:** Evidence files are stored completely outside the web document root and outside the application code directory (e.g. `/var/forensic_vault/`).
2. **UUID Content-Addressable Keys:** Files are never persisted using the user's uploaded filename. The platform generates an internal cryptographically secure UUIDv4 identifier:
   - *Original name:* `../../etc/shadow.jpg`
   - *Physical stored path:* `/var/forensic_vault/cases/3f9c6d54-.../evidence/a8e1b203-.../blob.bin`
   - *Database record:* Keeps `original_filename = "../../etc/shadow.jpg"` in sanitized escaped form for courtroom reporting.
3. **Strict Path Normalization:** All file retrieval utilities validate that the resolved path is strictly within the authorized vault root:
   ```python
   def secure_resolve_path(vault_root: Path, relative_key: str) -> Path:
       target = (vault_root / relative_key).resolve()
       if not target.is_relative_to(vault_root.resolve()):
           raise SecurityViolationException("Directory traversal attempt detected.")
       return target
   ```
4. **POSIX Read-Only Enforcement:** Immediately following file ingestion and hash validation, the file permissions are stripped down:
   ```python
   os.chmod(target_path, 0o400) # Read-only for owner, inaccessible to all others
   ```

---

### 5. Database Tamper Resistance & Audit Immutability

The integrity of forensic evidence relies on proving that records have not been altered in the database after the fact.

#### 5.1 Database-Level Immutability Enforcement
PostgreSQL triggers are installed via Alembic migrations to disallow any modification or deletion of evidence records and audit rows:

```sql
-- PostgreSQL Defense Trigger
CREATE OR REPLACE FUNCTION prevent_audit_tampering()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'CRITICAL SECURITY VIOLATION: Audit logs and evidence records are immutable and cannot be updated or deleted.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_immutable
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION prevent_audit_tampering();

CREATE TRIGGER trg_evidence_hash_immutable
BEFORE UPDATE OF primary_hash_sha256, hash_md5, hash_sha1, file_size_bytes ON evidence_items
FOR EACH ROW EXECUTE FUNCTION prevent_audit_tampering();
```

#### 5.2 Cryptographic Audit Chaining (Merkle / HMAC Chain)
Each audit entry contains:
- `previous_state_hash`: The SHA-256 digest of the immediately preceding audit event.
- `event_hash`: `HMAC-SHA256(secret_key, previous_hash + event_id + timestamp + payload)`.

Even if a malicious database administrator with superuser privileges directly disables database triggers and modifies a row, the cryptographic hash chain breaks, alerting the system during integrity audits.

---

### 6. Role-Based Access Control (RBAC) & Compartmentalization

The platform defines strict, least-privilege roles:

| Role | Permissions |
| :--- | :--- |
| **System Admin** | User onboarding, system health monitoring, worker status inspection. *Cannot view evidence content or delete case files.* |
| **Lead Investigator** | Create/Close cases, assign examiners, review all evidence in assigned cases, generate and sign final reports. |
| **Forensic Examiner** | Ingest evidence into assigned cases, execute forensic analyses, review visualizations, write examiner notes. |
| **External Auditor / Legal Counsel** | Read-only access to audit trail, hash verification histories, and generated reports. Cannot initiate new analyses. |
| **Viewer** | Read-only inspection of finalized public courtroom reports. |

Cross-case isolation is enforced in the domain service layer: users can only query cases to which they have been explicitly assigned by the Lead Investigator.
