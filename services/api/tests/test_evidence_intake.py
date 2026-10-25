"""
Comprehensive integration tests for secure evidence intake and integrity verification.

Tests:
1. Media categories (IMAGE, AUDIO, VIDEO)
2. Invalid files (empty file, unsupported executable disguise, corrupted bytes)
3. Oversized files (exceeding configurable size limit)
4. Traversal filenames (sanitization and vault containment)
5. Interrupted uploads (safe failure handling, zero orphan files, no phantom DB row)
6. Hash consistency and exact byte preservation
7. Independent hash verification (intact vs tampered file detection, integrity explanation)
8. Authorization enforcement (case ownership, viewer role rejection)
"""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import hash_password
from app.db.models.audit import AuditEvent, AuditEventType
from app.db.models.case import Case, CaseStatus
from app.db.models.evidence import EvidenceItem, HashVerification
from app.db.models.user import User, UserRole
from app.storage.local import LocalFilesystemStorageAdapter
from app.storage.manager import StorageManager

# ---------------------------------------------------------------------------
# Sample valid media bitstreams with authentic magic signatures
# ---------------------------------------------------------------------------

# Minimal 1x1 valid GIF89a image
VALID_GIF_BYTES = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)

# Minimal valid JPEG image header + payload
VALID_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
    b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
)

# Minimal valid PNG image
VALID_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\r\xef\x8c\x8e\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Valid WAV audio stream (RIFF + WAVE header)
VALID_WAV_BYTES = (
    b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
)

# Valid MP3 audio stream (ID3v2.3 container + sync frame)
VALID_MP3_BYTES = (
    b"ID3\x03\x00\x00\x00\x00\x00\x00\xff\xfb\x90\x64\x00\x00\x00\x00" + b"\x00" * 64
)

# Valid MP4 video stream (ftyp box with isom major brand)
VALID_MP4_BYTES = (
    b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free\x00\x00\x00\x08mdat"
)

# Valid Matroska / WebM video stream
VALID_WEBM_BYTES = (
    b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01\x42\xf2\x81\x04\x42\xf3\x81\x08\x42\x82\x84webm"
)


# ---------------------------------------------------------------------------
# Test fixtures & helpers
# ---------------------------------------------------------------------------


async def _create_test_user(
    db: AsyncSession,
    *,
    email: str,
    role: UserRole = UserRole.EXAMINER,
) -> User:
    """Create test user."""
    user = User(
        id=uuid4(),
        email=email.lower().strip(),
        hashed_password=hash_password("SecureEvidence1234!"),
        full_name="Forensic Investigator",
        role=role.value,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _create_test_case(
    db: AsyncSession,
    *,
    case_number: str,
    lead_id: UUID,
) -> Case:
    """Create test case."""
    case = Case(
        id=uuid4(),
        case_number=case_number.upper().strip(),
        title=f"Investigation {case_number}",
        status=CaseStatus.ACTIVE.value,
        lead_investigator_id=lead_id,
    )
    db.add(case)
    await db.flush()
    return case


async def _login_user(client: AsyncClient, email: str) -> str:
    """Login and return access token."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecureEvidence1234!"},
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test Suite: Three Media Categories
# ---------------------------------------------------------------------------


class TestMediaCategoriesUpload:
    @pytest.mark.asyncio
    async def test_upload_image_jpeg(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        """Verify JPEG image upload: 201 Created, media_type=IMAGE, SHA-256 correct."""
        user = await _create_test_user(test_db_session, email="investigator_img@test.com")
        case = await _create_test_case(test_db_session, case_number="CAS-IMG-001", lead_id=user.id)
        await test_db_session.commit()

        token = await _login_user(async_client, "investigator_img@test.com")
        expected_sha256 = hashlib.sha256(VALID_JPEG_BYTES).hexdigest()

        files = {"file": ("crime_scene.jpg", VALID_JPEG_BYTES, "image/jpeg")}
        resp = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/upload",
            files=files,
            headers=_auth_header(token),
        )

        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["media_type"] == "IMAGE"
        assert data["mime_type"] == "image/jpeg"
        assert data["file_size_bytes"] == len(VALID_JPEG_BYTES)
        assert data["primary_hash_sha256"] == expected_sha256
        assert data["intake_status"] == "INTACT"
        assert "authenticity" in data["integrity_notice"].lower()

    @pytest.mark.asyncio
    async def test_upload_image_png(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        """Verify PNG image upload."""
        user = await _create_test_user(test_db_session, email="investigator_png@test.com")
        case = await _create_test_case(test_db_session, case_number="CAS-PNG-001", lead_id=user.id)
        await test_db_session.commit()

        token = await _login_user(async_client, "investigator_png@test.com")
        expected_sha256 = hashlib.sha256(VALID_PNG_BYTES).hexdigest()

        files = {"file": ("screenshot.png", VALID_PNG_BYTES, "image/png")}
        resp = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/upload",
            files=files,
            headers=_auth_header(token),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["media_type"] == "IMAGE"
        assert data["mime_type"] == "image/png"
        assert data["primary_hash_sha256"] == expected_sha256

    @pytest.mark.asyncio
    async def test_upload_audio_wav_and_mp3(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        """Verify audio uploads (WAV & MP3): media_type=AUDIO."""
        user = await _create_test_user(test_db_session, email="investigator_aud@test.com")
        case = await _create_test_case(test_db_session, case_number="CAS-AUD-001", lead_id=user.id)
        await test_db_session.commit()

        token = await _login_user(async_client, "investigator_aud@test.com")

        # 1. WAV
        resp_wav = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/upload",
            files={"file": ("wiretap.wav", VALID_WAV_BYTES, "audio/wav")},
            headers=_auth_header(token),
        )
        assert resp_wav.status_code == 201
        assert resp_wav.json()["media_type"] == "AUDIO"
        assert resp_wav.json()["primary_hash_sha256"] == hashlib.sha256(VALID_WAV_BYTES).hexdigest()

        # 2. MP3
        resp_mp3 = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/upload",
            files={"file": ("voicemail.mp3", VALID_MP3_BYTES, "audio/mpeg")},
            headers=_auth_header(token),
        )
        assert resp_mp3.status_code == 201
        assert resp_mp3.json()["media_type"] == "AUDIO"
        assert resp_mp3.json()["primary_hash_sha256"] == hashlib.sha256(VALID_MP3_BYTES).hexdigest()

    @pytest.mark.asyncio
    async def test_upload_video_mp4_and_webm(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        """Verify video uploads (MP4 & WebM): media_type=VIDEO."""
        user = await _create_test_user(test_db_session, email="investigator_vid@test.com")
        case = await _create_test_case(test_db_session, case_number="CAS-VID-001", lead_id=user.id)
        await test_db_session.commit()

        token = await _login_user(async_client, "investigator_vid@test.com")

        # 1. MP4
        resp_mp4 = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/upload",
            files={"file": ("surveillance.mp4", VALID_MP4_BYTES, "video/mp4")},
            headers=_auth_header(token),
        )
        assert resp_mp4.status_code == 201
        assert resp_mp4.json()["media_type"] == "VIDEO"
        assert resp_mp4.json()["primary_hash_sha256"] == hashlib.sha256(VALID_MP4_BYTES).hexdigest()

        # 2. WebM
        resp_webm = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/upload",
            files={"file": ("cctv.webm", VALID_WEBM_BYTES, "video/webm")},
            headers=_auth_header(token),
        )
        assert resp_webm.status_code == 201
        assert resp_webm.json()["media_type"] == "VIDEO"


# ---------------------------------------------------------------------------
# Test Suite: Invalid Files and Mismatches
# ---------------------------------------------------------------------------


class TestInvalidFiles:
    @pytest.mark.asyncio
    async def test_reject_empty_file(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        """Empty file (0 bytes) must be rejected with 400 EMPTY_FILE."""
        user = await _create_test_user(test_db_session, email="empty_tester@test.com")
        case = await _create_test_case(test_db_session, case_number="CAS-EMPTY-01", lead_id=user.id)
        await test_db_session.commit()

        token = await _login_user(async_client, "empty_tester@test.com")

        files = {"file": ("empty.jpg", b"", "image/jpeg")}
        resp = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/upload",
            files=files,
            headers=_auth_header(token),
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "EMPTY_FILE"

    @pytest.mark.asyncio
    async def test_reject_executable_disguised_as_image(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        """Executable disguised as .jpg must be detected and rejected."""
        user = await _create_test_user(test_db_session, email="malware_tester@test.com")
        case = await _create_test_case(test_db_session, case_number="CAS-MAL-001", lead_id=user.id)
        await test_db_session.commit()

        token = await _login_user(async_client, "malware_tester@test.com")

        # Windows PE executable signature b"MZ..."
        fake_jpg = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00This is a virus payload"
        files = {"file": ("innocent_family_photo.jpg", fake_jpg, "image/jpeg")}

        resp = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/upload",
            files=files,
            headers=_auth_header(token),
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "UNSUPPORTED_MEDIA_TYPE"

    @pytest.mark.asyncio
    async def test_reject_pdf_disguised_as_mp3(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        """PDF document disguised as .mp3 must be rejected."""
        user = await _create_test_user(test_db_session, email="pdf_tester@test.com")
        case = await _create_test_case(test_db_session, case_number="CAS-PDF-001", lead_id=user.id)
        await test_db_session.commit()

        token = await _login_user(async_client, "pdf_tester@test.com")

        fake_mp3 = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj"
        files = {"file": ("recording.mp3", fake_mp3, "audio/mpeg")}

        resp = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/upload",
            files=files,
            headers=_auth_header(token),
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "UNSUPPORTED_MEDIA_TYPE"

    @pytest.mark.asyncio
    async def test_reject_unsupported_corrupt_bytes(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        """Arbitrary random bytes not matching any media format must be rejected."""
        user = await _create_test_user(test_db_session, email="corrupt_tester@test.com")
        case = await _create_test_case(test_db_session, case_number="CAS-COR-001", lead_id=user.id)
        await test_db_session.commit()

        token = await _login_user(async_client, "corrupt_tester@test.com")

        corrupt_data = b"Hello, this is just plain text, not media!"
        files = {"file": ("test.png", corrupt_data, "image/png")}

        resp = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/upload",
            files=files,
            headers=_auth_header(token),
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "INVALID_FILE_SIGNATURE"


# ---------------------------------------------------------------------------
# Test Suite: Oversized Files and Size Limits
# ---------------------------------------------------------------------------


class TestOversizedUploads:
    @pytest.mark.asyncio
    async def test_oversized_file_rejected_and_cleaned(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
        test_settings: Settings,
        test_storage: StorageManager,
    ) -> None:
        """File exceeding configured limit must return 413 and leave zero orphaned files."""
        user = await _create_test_user(test_db_session, email="size_tester@test.com")
        case = await _create_test_case(test_db_session, case_number="CAS-SIZE-01", lead_id=user.id)
        await test_db_session.commit()

        token = await _login_user(async_client, "size_tester@test.com")

        # Temporarily configure low limit: 200 bytes
        original_limit = test_settings.STORAGE_MAX_UPLOAD_SIZE_BYTES
        test_settings.STORAGE_MAX_UPLOAD_SIZE_BYTES = 200

        try:
            # Create a 2 KB JPEG (starts with valid JPEG header + padding)
            oversized_jpeg = VALID_JPEG_BYTES + (b"\x00" * 2048)
            files = {"file": ("big_image.jpg", oversized_jpeg, "image/jpeg")}

            resp = await async_client.post(
                f"/api/v1/cases/{case.id}/evidence/upload",
                files=files,
                headers=_auth_header(token),
            )
            assert resp.status_code == 413
            assert resp.json()["detail"]["code"] == "FILE_TOO_LARGE"

            # Verify NO evidence item was created in DB
            stmt = select(EvidenceItem).where(EvidenceItem.case_id == case.id)
            db_res = await test_db_session.execute(stmt)
            assert db_res.scalar_one_or_none() is None

            # Verify tmp scratch directory has no orphaned staging files
            staged_files = list(test_storage.tmp_path.glob(".txn_stage_*.tmp"))
            assert len(staged_files) == 0

        finally:
            test_settings.STORAGE_MAX_UPLOAD_SIZE_BYTES = original_limit


# ---------------------------------------------------------------------------
# Test Suite: Traversal Filename Sanitization
# ---------------------------------------------------------------------------


class TestPathTraversalFilenames:
    @pytest.mark.asyncio
    async def test_traversal_filename_is_sanitized(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
        test_storage_adapter: LocalFilesystemStorageAdapter,
    ) -> None:
        """Filename with path traversal dots/slashes is sanitized and safely contained."""
        user = await _create_test_user(test_db_session, email="traversal_user@test.com")
        case = await _create_test_case(test_db_session, case_number="CAS-TRAV-01", lead_id=user.id)
        await test_db_session.commit()

        token = await _login_user(async_client, "traversal_user@test.com")

        malicious_filename = "../../../../etc/shadow.png"
        files = {"file": (malicious_filename, VALID_PNG_BYTES, "image/png")}

        resp = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/upload",
            files=files,
            headers=_auth_header(token),
        )
        assert resp.status_code == 201
        data = resp.json()

        # The display filename should NOT contain .. or /
        assert ".." not in data["original_filename"]
        assert "/" not in data["original_filename"]
        assert "\\" not in data["original_filename"]

        # The storage key must be within originals/cases/{case.id}/
        assert f"cases/{case.id}" in data["storage_path"]
        assert ".." not in data["storage_path"]

        # Verify physical file is safely inside the originals vault via adapter
        assert test_storage_adapter.exists(data["storage_path"])


# ---------------------------------------------------------------------------
# Test Suite: Interrupted Upload Failure Handling
# ---------------------------------------------------------------------------


class TestInterruptedUploads:
    @pytest.mark.asyncio
    async def test_interrupted_upload_leaves_no_phantom_record_or_orphan(
        self,
        test_db_session: AsyncSession,
        test_storage_adapter: LocalFilesystemStorageAdapter,
        test_storage: StorageManager,
    ) -> None:
        """Simulate an interrupted stream; verify rollback and cleanup."""
        from app.storage.transaction import StagedStorageTransaction

        user = await _create_test_user(test_db_session, email="interrupt_user@test.com")
        case = await _create_test_case(test_db_session, case_number="CAS-INT-001", lead_id=user.id)
        await test_db_session.commit()

        storage_key = test_storage_adapter.generate_key("originals", case.id, "interrupted.png")

        class BrokenStream:
            """Stream that throws an unexpected connection abort after 1st chunk."""

            def __init__(self) -> None:
                self.count = 0

            async def read(self, size: int) -> bytes:
                self.count += 1
                if self.count == 1:
                    return b"some initial bytes"
                raise ConnectionResetError("Client network connection abruptly severed!")

        broken = BrokenStream()

        # Attempt transaction with failing stream
        with pytest.raises(Exception):
            with StagedStorageTransaction(test_storage_adapter) as txn:
                await txn.stage_stream(key=storage_key, stream=broken, initial_chunk=VALID_PNG_BYTES[:16])

        # Verify no staged file remains in tmp
        staged_files = list(test_storage.tmp_path.glob(".txn_stage_*.tmp"))
        assert len(staged_files) == 0

        # Verify no permanent file exists
        assert not test_storage_adapter.exists(storage_key)

        # Verify no database record exists
        stmt = select(EvidenceItem).where(EvidenceItem.case_id == case.id)
        res = await test_db_session.execute(stmt)
        assert res.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Test Suite: Hash Consistency & Exact Byte Preservation
# ---------------------------------------------------------------------------


class TestHashConsistencyAndPreservation:
    @pytest.mark.asyncio
    async def test_exact_byte_preservation_and_hash_consistency(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
        test_storage_adapter: LocalFilesystemStorageAdapter,
    ) -> None:
        """Confirm that stored bytes exactly match uploaded bytes and all hashes are consistent."""
        user = await _create_test_user(test_db_session, email="hash_user@test.com")
        case = await _create_test_case(test_db_session, case_number="CAS-HASH-01", lead_id=user.id)
        await test_db_session.commit()

        token = await _login_user(async_client, "hash_user@test.com")

        # Build custom valid JPEG with specific extra padding bytes
        custom_payload = VALID_JPEG_BYTES + b"\x01\x02\x03\x04\x05\xaa\xbb\xcc\xdd\xee"
        expected_sha256 = hashlib.sha256(custom_payload).hexdigest()
        expected_md5 = hashlib.md5(custom_payload).hexdigest()
        expected_sha1 = hashlib.sha1(custom_payload).hexdigest()

        resp = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/upload",
            files={"file": ("exact_test.jpg", custom_payload, "image/jpeg")},
            headers=_auth_header(token),
        )
        assert resp.status_code == 201
        data = resp.json()

        # Database record hash matches client calculation
        assert data["primary_hash_sha256"] == expected_sha256
        assert data["hash_md5"] == expected_md5
        assert data["hash_sha1"] == expected_sha1
        assert data["file_size_bytes"] == len(custom_payload)

        # Read actual physical bytes from private storage
        stored_bytes = test_storage_adapter.read(data["storage_path"])
        assert stored_bytes == custom_payload
        assert hashlib.sha256(stored_bytes).hexdigest() == expected_sha256


# ---------------------------------------------------------------------------
# Test Suite: Independent Hash Verification & Authenticity Notice
# ---------------------------------------------------------------------------


class TestIndependentHashVerification:
    @pytest.mark.asyncio
    async def test_independent_verification_intact_and_tampered(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
        test_storage_adapter: LocalFilesystemStorageAdapter,
    ) -> None:
        """Verify baseline check succeeds on intact file, fails on tampered file, and includes legal notice."""
        user = await _create_test_user(test_db_session, email="verifier_user@test.com")
        case = await _create_test_case(test_db_session, case_number="CAS-VERIF-01", lead_id=user.id)
        await test_db_session.commit()

        token = await _login_user(async_client, "verifier_user@test.com")

        # 1. Upload evidence
        up_resp = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/upload",
            files={"file": ("camera_recording.mp4", VALID_MP4_BYTES, "video/mp4")},
            headers=_auth_header(token),
        )
        assert up_resp.status_code == 201
        ev_data = up_resp.json()
        evidence_id = ev_data["id"]

        # 2. Re-verify intact file independently
        verif_resp = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/{evidence_id}/verify-hash",
            headers=_auth_header(token),
        )
        assert verif_resp.status_code == 200
        v_data = verif_resp.json()
        assert v_data["is_intact"] is True
        assert v_data["calculated_sha256"] == ev_data["primary_hash_sha256"]
        assert "authenticity" in v_data["integrity_notice"].lower()

        # Check HashVerification record in DB
        stmt = select(HashVerification).where(HashVerification.evidence_id == UUID(evidence_id))
        res = await test_db_session.execute(stmt)
        verifications = res.scalars().all()
        assert len(verifications) >= 2  # Baseline at intake + re-verification
        assert all(v.is_intact for v in verifications)

        # 3. Tamper test: Alter 1 single byte of stored file on disk
        target_path = test_storage_adapter.get_local_path_readonly(ev_data["storage_path"])
        import stat

        target_path.chmod(stat.S_IWRITE | stat.S_IWUSR)
        with open(target_path, "r+b") as f:
            f.seek(0)
            f.write(b"\x99")  # Flip first byte
        target_path.chmod(stat.S_IREAD | stat.S_IRUSR)

        # 4. Re-verify tampered file
        tamper_resp = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/{evidence_id}/verify-hash",
            headers=_auth_header(token),
        )
        assert tamper_resp.status_code == 200
        t_data = tamper_resp.json()
        assert t_data["is_intact"] is False
        assert t_data["calculated_sha256"] != ev_data["primary_hash_sha256"]

        # Check AuditEvent logged TAMPER_DETECTED
        audit_stmt = select(AuditEvent).where(
            AuditEvent.evidence_id == UUID(evidence_id),
            AuditEvent.event_type == AuditEventType.TAMPER_DETECTED.value,
        )
        audit_res = await test_db_session.execute(audit_stmt)
        tamper_event = audit_res.scalar_one_or_none()
        assert tamper_event is not None
        assert "CRITICAL" in tamper_event.action_description


# ---------------------------------------------------------------------------
# Test Suite: Case-Level Authorization
# ---------------------------------------------------------------------------


class TestEvidenceAuthorization:
    @pytest.mark.asyncio
    async def test_examiner_cannot_upload_to_another_users_case(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        """Examiner B cannot upload evidence into Examiner A's case (403)."""
        owner = await _create_test_user(test_db_session, email="owner_examiner@test.com")
        attacker = await _create_test_user(test_db_session, email="attacker_examiner@test.com")
        case = await _create_test_case(test_db_session, case_number="CAS-RESTRICTED", lead_id=owner.id)
        await test_db_session.commit()

        attacker_token = await _login_user(async_client, "attacker_examiner@test.com")

        files = {"file": ("unauthorized.png", VALID_PNG_BYTES, "image/png")}
        resp = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/upload",
            files=files,
            headers=_auth_header(attacker_token),
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "CASE_ACCESS_DENIED"

    @pytest.mark.asyncio
    async def test_viewer_role_cannot_upload_evidence(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        """Viewer role has read-only access and cannot upload evidence (403)."""
        viewer = await _create_test_user(
            test_db_session,
            email="viewer_user@test.com",
            role=UserRole.VIEWER,
        )
        case = await _create_test_case(test_db_session, case_number="CAS-VIEW-01", lead_id=viewer.id)
        await test_db_session.commit()

        viewer_token = await _login_user(async_client, "viewer_user@test.com")

        files = {"file": ("attempt.jpg", VALID_JPEG_BYTES, "image/jpeg")}
        resp = await async_client.post(
            f"/api/v1/cases/{case.id}/evidence/upload",
            files=files,
            headers=_auth_header(viewer_token),
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "INSUFFICIENT_PERMISSIONS"
