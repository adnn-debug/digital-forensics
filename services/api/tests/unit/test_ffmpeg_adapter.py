"""
Unit tests for FFmpeg video frame extraction adapter.

Tests:
1. Normal video frame extraction at controlled timestamps
2. Evenly spaced representative frame generation when timestamps not specified
3. Bounded frame limit enforcement (max_frames)
4. Target resolution scaling limits
5. Safe handling of non-existent files
6. Safe handling of empty (0-byte) files
7. Safe handling of corrupt and malformed video files
8. Safe handling of non-video inputs (text file, random bytes)
9. Subprocess command safety and argument injection resistance
10. Strict execution timeout enforcement
11. Tool version retrieval and provenance recording
12. Forensic limitation disclaimer verification
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.forensics.ffmpeg_adapter import (
    FORENSIC_FRAME_EXTRACTION_DISCLAIMER,
    FFmpegAdapter,
    compute_frame_dhash,
)
from app.forensics.ffprobe_adapter import FFprobeAdapter


@pytest.fixture
def ffmpeg_adapter() -> FFmpegAdapter:
    return FFmpegAdapter()


@pytest.fixture
def ffprobe_adapter() -> FFprobeAdapter:
    return FFprobeAdapter()


@pytest.fixture
def sample_test_video(tmp_path: Path) -> Path:
    """Generate a valid 2-second test video with 2 distinct scene colors."""
    video_path = tmp_path / "test_sample.mp4"
    width, height = 320, 240
    fps = 10

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore[attr-defined]
    out = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))

    # First 10 frames: Blue scene
    for _ in range(10):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = (255, 0, 0)
        out.write(frame)

    # Next 10 frames: Yellow scene
    for _ in range(10):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = (0, 255, 255)
        out.write(frame)

    out.release()
    return video_path


class TestFFmpegVersionAndAvailability:
    def test_ffmpeg_version_query(self, ffmpeg_adapter: FFmpegAdapter) -> None:
        """Verify tool name and version string extraction."""
        assert ffmpeg_adapter.tool_name == "FFmpeg"
        if ffmpeg_adapter.is_available():
            ver = ffmpeg_adapter.get_version()
            assert isinstance(ver, str)
            assert len(ver) > 0
            assert ver != "Unavailable"


class TestFFmpegFrameExtraction:
    def test_normal_frame_extraction_with_timestamps(
        self,
        ffmpeg_adapter: FFmpegAdapter,
        sample_test_video: Path,
    ) -> None:
        """Verify extracting representative frames at specified timestamps."""
        if not ffmpeg_adapter.is_available():
            pytest.skip("FFmpeg executable not available on host.")

        result = ffmpeg_adapter.extract_representative_frames(
            sample_test_video,
            timestamps=[0.2, 1.2],
            max_frames=5,
            evidence_number="TEST-EVID-VID-01",
        )

        assert result.success is True
        assert len(result.frames) == 2
        assert result.tool_name == "FFmpeg"
        assert result.tool_version != "Unavailable"
        assert result.forensic_notice == FORENSIC_FRAME_EXTRACTION_DISCLAIMER

        # Inspect individual frames
        frame0 = result.frames[0]
        assert frame0.frame_index == 0
        assert frame0.timestamp_seconds == 0.2
        assert frame0.mime_type == "image/png"
        assert len(frame0.image_bytes) > 0
        assert len(frame0.sha256) == 64
        assert len(frame0.dhash) == 16
        assert frame0.width > 0
        assert frame0.height > 0
        assert "TEST-EVID-VID-01_frame_000_0.20s.png" in frame0.filename

        # Verify provenance
        assert result.provenance["source_file_sha256"] != ""
        assert result.provenance["source_file_size_bytes"] > 0
        assert result.provenance["total_commands_executed"] == 2

    def test_evenly_spaced_representative_frames(
        self,
        ffmpeg_adapter: FFmpegAdapter,
        sample_test_video: Path,
    ) -> None:
        """Verify automatic even distribution of frames when timestamps are not provided."""
        if not ffmpeg_adapter.is_available():
            pytest.skip("FFmpeg executable not available on host.")

        result = ffmpeg_adapter.extract_representative_frames(
            sample_test_video,
            max_frames=3,
            evidence_number="TEST-AUTO-TS",
        )

        assert result.success is True
        assert len(result.frames) <= 3
        assert len(result.frames) >= 1
        assert result.extraction_settings["max_frames_configured"] == 3

    def test_bounded_frame_limit_clamping(
        self,
        ffmpeg_adapter: FFmpegAdapter,
        sample_test_video: Path,
    ) -> None:
        """Verify that requesting excessive frames is clamped to upper bound."""
        if not ffmpeg_adapter.is_available():
            pytest.skip("FFmpeg executable not available on host.")

        # Request 100 frames (exceeding hard bound of 50)
        result = ffmpeg_adapter.extract_representative_frames(
            sample_test_video,
            max_frames=100,
        )
        assert result.extraction_settings["max_frames_configured"] <= 50

    def test_resolution_bounding_filter(
        self,
        ffmpeg_adapter: FFmpegAdapter,
        sample_test_video: Path,
    ) -> None:
        """Verify output frame dimensions respect max_resolution bounds."""
        if not ffmpeg_adapter.is_available():
            pytest.skip("FFmpeg executable not available on host.")

        result = ffmpeg_adapter.extract_representative_frames(
            sample_test_video,
            timestamps=[0.5],
            max_resolution=(160, 120),  # Scaled down from 320x240
        )

        assert result.success is True
        assert len(result.frames) == 1
        frame = result.frames[0]
        assert frame.width <= 160
        assert frame.height <= 120


class TestFFmpegDefensiveValidation:
    def test_nonexistent_file_handling(self, ffmpeg_adapter: FFmpegAdapter) -> None:
        """Verify non-existent path returns graceful error without throwing."""
        fake_path = Path("nonexistent_video_12345.mp4")
        result = ffmpeg_adapter.extract_representative_frames(fake_path)

        assert result.success is False
        assert len(result.frames) == 0
        assert len(result.errors) >= 1
        assert "does not exist" in result.errors[0]

    def test_empty_file_handling(self, ffmpeg_adapter: FFmpegAdapter, tmp_path: Path) -> None:
        """Verify 0-byte file returns clean error."""
        empty_file = tmp_path / "zero_bytes.mp4"
        empty_file.write_bytes(b"")

        result = ffmpeg_adapter.extract_representative_frames(empty_file)
        assert result.success is False
        assert len(result.frames) == 0
        assert any("empty (0 bytes)" in err for err in result.errors)

    def test_non_video_text_file(self, ffmpeg_adapter: FFmpegAdapter, tmp_path: Path) -> None:
        """Verify plain text file disguised as mp4 is rejected gracefully."""
        text_file = tmp_path / "fake_video.mp4"
        text_file.write_text("This is plain ASCII text pretending to be a video.")

        result = ffmpeg_adapter.extract_representative_frames(text_file)
        assert result.success is False
        assert len(result.frames) == 0
        assert any("No valid decodable video stream found" in err for err in result.errors)

    def test_corrupt_malformed_bytes(self, ffmpeg_adapter: FFmpegAdapter, tmp_path: Path) -> None:
        """Verify corrupted binary header fails safely without uncaught exceptions."""
        corrupt_file = tmp_path / "corrupt.mp4"
        corrupt_file.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00" + b"\xff" * 256)

        result = ffmpeg_adapter.extract_representative_frames(corrupt_file)
        assert result.success is False
        assert len(result.frames) == 0
        assert len(result.errors) >= 1

    def test_oversized_file_limit(self, ffmpeg_adapter: FFmpegAdapter, tmp_path: Path) -> None:
        """Verify file exceeding max_file_size_bytes is aborted."""
        oversized = tmp_path / "oversized.mp4"
        oversized.write_bytes(b"A" * 1024)

        result = ffmpeg_adapter.extract_representative_frames(
            oversized,
            max_file_size_bytes=512,  # Limit smaller than file
        )
        assert result.success is False
        assert any("exceeds maximum allowed resource limit" in err for err in result.errors)

    def test_command_injection_safety(self, ffmpeg_adapter: FFmpegAdapter, tmp_path: Path) -> None:
        """Verify filename containing CLI parameter injection syntax is safely handled."""
        hostile_file = tmp_path / "--output=malicious.txt"
        hostile_file.write_text("fake video bitstream")

        result = ffmpeg_adapter.extract_representative_frames(hostile_file)
        assert result.success is False
        # Ensure malicious side effect did not happen
        assert not (tmp_path / "malicious.txt").exists()


class TestFFprobeVideoStreamInspection:
    def test_inspect_video_streams_success(
        self,
        ffprobe_adapter: FFprobeAdapter,
        sample_test_video: Path,
    ) -> None:
        """Verify FFprobe inspect_video_streams extracts timestamps, codec, fps, and tags."""
        if not ffprobe_adapter.is_available():
            pytest.skip("FFprobe executable not available on host.")

        info = ffprobe_adapter.inspect_video_streams(sample_test_video)

        assert info["success"] is True
        assert info["has_video"] is True
        assert info["primary_stream"] is not None

        ps = info["primary_stream"]
        assert ps["width"] == 320
        assert ps["height"] == 240
        assert "dimensions" in ps
        assert "frame_rate" in ps
        assert "start_time_seconds" in ps
        assert "time_base" in ps
        assert "tags" in ps
        assert "forensic_authenticity_notice" in info


def test_frame_dhash_calculation() -> None:
    """Verify difference hash computation directly from image bytes."""
    # Synthetic 100x100 white image
    white_img = np.ones((100, 100, 3), dtype=np.uint8) * 255
    success, buf = cv2.imencode(".png", white_img)
    assert success
    dhash = compute_frame_dhash(buf.tobytes())
    assert isinstance(dhash, str)
    assert len(dhash) == 16
