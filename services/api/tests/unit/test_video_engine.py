"""Unit tests for VideoForensicsEngine."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.forensics.video_engine import VideoForensicsEngine, compute_dhash
from app.storage.hasher import MultiHasher


@pytest.fixture
def sample_video_path(tmp_path: Path) -> Path:
    """Create a synthetic 1-second video with a scene cut at 0.5s."""
    video_file = tmp_path / "test_evidence.mp4"
    width, height = 160, 120
    fps = 10
    total_frames = 10

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore[attr-defined]
    out = cv2.VideoWriter(str(video_file), fourcc, fps, (width, height))

    # First 5 frames: red scene
    for _ in range(5):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = (0, 0, 255)
        out.write(frame)

    # Next 5 frames: green scene (drastic cut)
    for _ in range(5):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = (0, 255, 0)
        out.write(frame)

    out.release()
    return video_file


def test_dhash_calculation() -> None:
    """Verify difference hash computation on synthetic image array."""
    gray = np.zeros((50, 50), dtype=np.uint8)
    gray[:, 25:] = 255  # Left-to-right gradient step
    h = compute_dhash(gray)
    assert isinstance(h, str)
    assert len(h) == 16


def test_video_engine_analysis(sample_video_path: Path) -> None:
    """Verify VideoForensicsEngine extracts properties, keyframes, and scene cuts."""
    hasher = MultiHasher()
    digests = hasher.hash_file(sample_video_path)

    engine = VideoForensicsEngine(max_keyframes=5)
    result = engine.analyze_file(
        file_path=sample_video_path,
        expected_sha256=digests.sha256,
        evidence_number="TEST-VID-01",
    )

    assert result.hash_integrity.is_intact is True
    assert result.properties.is_valid_stream is True
    assert result.properties.width == 160
    assert result.properties.height == 120
    assert result.properties.total_frames == 10
    assert len(result.keyframes) >= 1

    # Check keyframe structure
    kf = result.keyframes[0]
    assert kf.mime_type == "image/png"
    assert len(kf.image_bytes) > 0
    assert len(kf.dhash) == 16

    summary = result.to_summary_dict()
    assert "container_properties" in summary
    assert "keyframes" in summary
    assert "temporal_metrics" in summary


def test_video_engine_tamper_detection(sample_video_path: Path) -> None:
    """Verify mismatch between expected SHA-256 and bitstream raises critical finding."""
    engine = VideoForensicsEngine()
    fake_hash = "0" * 64

    result = engine.analyze_file(
        file_path=sample_video_path,
        expected_sha256=fake_hash,
        evidence_number="TEST-VID-02",
    )

    assert result.hash_integrity.is_intact is False
    tamper_findings = [f for f in result.findings if f.finding_type == "HASH_TAMPER"]
    assert len(tamper_findings) == 1
    assert tamper_findings[0].severity == "CRITICAL"
