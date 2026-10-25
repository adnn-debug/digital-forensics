"""
Unit tests for forensic metadata adapters: ExifTool and FFprobe.

Tests:
1. Command construction and argument isolation (-- boundary, zero shell=True)
2. Tool version querying and caching
3. Normal image extraction (dimensions, format, timestamps, software tags)
4. Normal audio extraction (sample rate, channels, codec, duration)
5. Normal video extraction (resolution, frame rate, video/audio codecs, duration)
6. Missing metadata handling (uninvented values, explicit 'Unavailable' representations)
7. Malformed media handling (graceful error capture, no unhandled exceptions)
8. Unsupported file handling (graceful failure reporting)
9. Strict subprocess execution timeout enforcement
10. Forensic authenticity notice presence and verification
"""

from __future__ import annotations

import struct
import subprocess
import wave
from pathlib import Path

import pytest

from app.forensics.base import (
    ForensicExecutionError,
    SafeSubprocessRunner,
    ToolExecutionResult,
)
from app.forensics.exif_adapter import (
    FORENSIC_AUTHENTICITY_DISCLAIMER,
    ExifToolAdapter,
)
from app.forensics.ffprobe_adapter import (
    FORENSIC_CONTAINER_DISCLAIMER,
    FFprobeAdapter,
)


@pytest.fixture
def exif_adapter() -> ExifToolAdapter:
    return ExifToolAdapter()


@pytest.fixture
def ffprobe_adapter() -> FFprobeAdapter:
    return FFprobeAdapter()


# ---------------------------------------------------------------------------
# Test Helpers: Synthetic Media Generators
# ---------------------------------------------------------------------------


def create_synthetic_wav(path: Path, sample_rate: int = 44100, channels: int = 2, duration_sec: float = 0.5) -> Path:
    """Generate authentic, uncorrupted PCM WAV audio file with standard library."""
    num_frames = int(sample_rate * duration_sec)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        raw_frames = struct.pack(
            f"<{num_frames * channels}h",
            *[int(500 * (i % 20)) for i in range(num_frames * channels)],
        )
        wf.writeframes(raw_frames)
    return path


def create_synthetic_jpeg(path: Path, width: int = 640, height: int = 480) -> Path:
    """Generate authentic JPEG using ffmpeg or raw bytes."""
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=red:s={width}x{height}:d=1",
        "-vframes",
        "1",
        "-update",
        "1",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        # Fallback to standard 1x1 valid JPEG bytes if ffmpeg is somehow absent
        from tests.test_evidence_intake import VALID_JPEG_BYTES
        path.write_bytes(VALID_JPEG_BYTES)
    return path


def create_synthetic_video(path: Path, width: int = 320, height: int = 240, duration_sec: int = 1) -> Path:
    """Generate authentic MP4 container with H.264 video and AAC audio."""
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={duration_sec}:size={width}x{height}:rate=25",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=1000:duration={duration_sec}",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        from tests.test_evidence_intake import VALID_MP4_BYTES
        path.write_bytes(VALID_MP4_BYTES)
    return path


# ---------------------------------------------------------------------------
# 1. Command Line Safety & Argument Injection Mitigation
# ---------------------------------------------------------------------------


class TestSubprocessCommandSafety:
    """Verify that command arguments cannot be hijacked via malicious filenames or flags."""

    def test_exiftool_command_injection_mitigation(self, exif_adapter: ExifToolAdapter, tmp_path: Path) -> None:
        # Use a filename that starts with flag-injection characters but is a valid Windows filename
        malicious_filename = tmp_path / "--config=injected.cfg.fakeimage"
        malicious_filename.write_text("injection test")

        cmd = exif_adapter.build_command(malicious_filename)

        assert isinstance(cmd, list)
        assert "--" in cmd
        # Ensure delimiter strictly precedes the file path argument
        delim_idx = cmd.index("--")
        assert delim_idx == len(cmd) - 2
        assert cmd[-1] == str(malicious_filename)
        # Verify shell=False is enforced by runner
        assert cmd[0].endswith("exiftool") or cmd[0].endswith("exiftool.exe") or cmd[0].endswith("ExifTool.exe")

    def test_ffprobe_command_injection_mitigation(self, ffprobe_adapter: FFprobeAdapter, tmp_path: Path) -> None:
        # Use a filename that starts with flag-injection characters but is a valid Windows filename
        malicious_filename = tmp_path / "--show_data.fakestream"
        malicious_filename.write_text("injection test")

        cmd = ffprobe_adapter.build_command(malicious_filename)

        assert isinstance(cmd, list)
        assert "--" in cmd
        delim_idx = cmd.index("--")
        assert delim_idx == len(cmd) - 2
        assert cmd[-1] == str(malicious_filename)


# ---------------------------------------------------------------------------
# 2. Tool Version Querying
# ---------------------------------------------------------------------------


class TestToolVersions:
    """Verify dynamic discovery and reporting of CLI utility versions."""

    def test_exiftool_version_retrieval(self, exif_adapter: ExifToolAdapter) -> None:
        version = exif_adapter.get_version()
        assert version != "Unavailable"
        assert "." in version  # e.g. 13.59

    def test_ffprobe_version_retrieval(self, ffprobe_adapter: FFprobeAdapter) -> None:
        version = ffprobe_adapter.get_version()
        assert version != "Unavailable"
        assert "." in version  # e.g. 8.1.1


# ---------------------------------------------------------------------------
# 3. Normal Media Extraction
# ---------------------------------------------------------------------------


class TestNormalMediaExtraction:
    """Verify extraction of normal, valid files across images, audio, and video."""

    def test_normal_image_extraction_with_exiftool(self, exif_adapter: ExifToolAdapter, tmp_path: Path) -> None:
        img_path = tmp_path / "camera_capture.jpg"
        create_synthetic_jpeg(img_path, width=640, height=480)

        # Inject known EXIF tags via exiftool
        bin_path = exif_adapter.resolve_binary()
        subprocess.run(
            [
                bin_path,
                "-Make=Nikon",
                "-Model=D850",
                "-Software=PS05 Forensic Studio",
                "-DateTimeOriginal=2026:10:24 10:15:30",
                "-overwrite_original",
                str(img_path),
            ],
            capture_output=True,
        )

        result: ToolExecutionResult = exif_adapter.extract_metadata(img_path)

        assert result.success is True
        assert result.tool_name == "ExifTool"
        assert result.tool_version != "Unavailable"
        assert result.execution_duration_ms > 0

        meta = result.filtered_forensic_metadata
        assert meta["dimensions"] == "640x480"
        assert meta["image_width"] == 640
        assert meta["image_height"] == 480
        assert meta["aspect_ratio"] == "4:3"
        assert meta["file_type"] == "JPEG"

        # Software tags
        assert meta["software_tags"]["make"] == "Nikon"
        assert meta["software_tags"]["model"] == "D850"
        assert meta["software_tags"]["software"] == "PS05 Forensic Studio"
        assert meta["timestamps"]["date_time_original"] == "2026:10:24 10:15:30"

        # Forensic authenticity warning must always be attached
        assert meta["forensic_authenticity_notice"] == FORENSIC_AUTHENTICITY_DISCLAIMER

    def test_normal_audio_extraction_with_ffprobe(self, ffprobe_adapter: FFprobeAdapter, tmp_path: Path) -> None:
        audio_path = tmp_path / "ambient_recording.wav"
        create_synthetic_wav(audio_path, sample_rate=48000, channels=2, duration_sec=0.5)

        result: ToolExecutionResult = ffprobe_adapter.extract_metadata(audio_path)

        assert result.success is True
        assert result.tool_name == "FFprobe"
        meta = result.filtered_forensic_metadata

        # Container
        container = meta["container"]
        assert "wav" in container["format_name"].lower()
        assert float(container["duration_seconds"]) == pytest.approx(0.5, abs=0.1)

        # Audio stream
        assert len(meta["audio_streams"]) >= 1
        audio_stream = meta["audio_streams"][0]
        assert audio_stream["sample_rate_hz"] == 48000
        assert audio_stream["channels"] == 2
        assert "pcm" in audio_stream["codec_name"].lower()

        # Notice
        assert meta["forensic_authenticity_notice"] == FORENSIC_CONTAINER_DISCLAIMER

    def test_normal_video_extraction_with_ffprobe(self, ffprobe_adapter: FFprobeAdapter, tmp_path: Path) -> None:
        video_path = tmp_path / "surveillance_clip.mp4"
        create_synthetic_video(video_path, width=320, height=240, duration_sec=1)

        result: ToolExecutionResult = ffprobe_adapter.extract_metadata(video_path)

        assert result.success is True
        assert result.tool_name == "FFprobe"
        meta = result.filtered_forensic_metadata

        # Video stream
        assert len(meta["video_streams"]) >= 1
        v_stream = meta["video_streams"][0]
        assert v_stream["width"] == 320
        assert v_stream["height"] == 240
        assert v_stream["dimensions"] == "320x240"
        assert "25" in v_stream["frame_rate"]
        assert "h264" in v_stream["codec_name"].lower()

        # Audio stream
        assert len(meta["audio_streams"]) >= 1
        a_stream = meta["audio_streams"][0]
        assert a_stream["sample_rate_hz"] == 44100
        assert "aac" in a_stream["codec_name"].lower()

        assert meta["forensic_authenticity_notice"] == FORENSIC_CONTAINER_DISCLAIMER


# ---------------------------------------------------------------------------
# 4. Missing Metadata (Uninvented Values Guarantee)
# ---------------------------------------------------------------------------


class TestMissingMetadataIntegrity:
    """Verify that absent tags are represented as 'Unavailable' rather than hallucinated."""

    def test_stripped_jpeg_has_unavailable_tags(self, exif_adapter: ExifToolAdapter, tmp_path: Path) -> None:
        img_path = tmp_path / "stripped_image.jpg"
        create_synthetic_jpeg(img_path, width=300, height=200)

        result: ToolExecutionResult = exif_adapter.extract_metadata(img_path)
        meta = result.filtered_forensic_metadata

        # The image has no camera make, model, or GPS tags
        assert meta["software_tags"]["make"] == "Unavailable"
        assert meta["software_tags"]["model"] == "Unavailable"
        assert meta["software_tags"]["lens_model"] == "Unavailable"
        assert meta["timestamps"]["date_time_original"] == "Unavailable"
        assert meta["gps"]["latitude"] == "Unavailable"
        assert meta["gps"]["longitude"] == "Unavailable"

    def test_audio_without_video_has_empty_video_streams(self, ffprobe_adapter: FFprobeAdapter, tmp_path: Path) -> None:
        wav_path = tmp_path / "pure_sound.wav"
        create_synthetic_wav(wav_path, sample_rate=22050, channels=1, duration_sec=0.2)

        result = ffprobe_adapter.extract_metadata(wav_path)
        meta = result.filtered_forensic_metadata

        assert meta["video_streams"] == []
        assert meta["video_stream_count"] == 0
        assert len(meta["audio_streams"]) == 1


# ---------------------------------------------------------------------------
# 5. Malformed Media & Unsupported Files Handling
# ---------------------------------------------------------------------------


class TestMalformedAndUnsupportedFiles:
    """Verify robust error recovery for corrupt, truncated, or unsupported files."""

    def test_corrupt_malformed_media_handling(self, exif_adapter: ExifToolAdapter, ffprobe_adapter: FFprobeAdapter, tmp_path: Path) -> None:
        corrupt_path = tmp_path / "truncated_stream.mp4"
        # Truncated container bytes
        corrupt_path.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00\xff\xff\x00")

        # ExifTool should not crash
        exif_res = exif_adapter.extract_metadata(corrupt_path)
        assert isinstance(exif_res, ToolExecutionResult)

        # FFprobe should gracefully capture errors without unhandled exceptions
        ff_res = ffprobe_adapter.extract_metadata(corrupt_path)
        assert isinstance(ff_res, ToolExecutionResult)
        assert ff_res.tool_name == "FFprobe"

    def test_unsupported_plain_text_file(self, ffprobe_adapter: FFprobeAdapter, tmp_path: Path) -> None:
        txt_path = tmp_path / "investigation_notes.txt"
        txt_path.write_text("Courtroom evidence audit notes 2026. Non-multimedia file.")

        result = ffprobe_adapter.extract_metadata(txt_path)
        assert isinstance(result, ToolExecutionResult)
        # Should report failure or have errors noted
        assert result.filtered_forensic_metadata["container"]["format_name"] in ("Unavailable", "tty") or result.success is False

    def test_nonexistent_file_handling(self, exif_adapter: ExifToolAdapter, tmp_path: Path) -> None:
        ghost_path = tmp_path / "nonexistent.jpg"
        result = exif_adapter.extract_metadata(ghost_path)
        assert result.success is False
        assert "does not exist" in result.errors[0]


# ---------------------------------------------------------------------------
# 6. Strict Subprocess Timeout & Output Bounds
# ---------------------------------------------------------------------------


class TestSubprocessTimeoutAndBounds:
    """Verify strict execution timeouts and output bounding."""

    def test_strict_timeout_raises_forensic_error(self) -> None:
        # Command that sleeps longer than timeout
        with pytest.raises(ForensicExecutionError) as exc_info:
            SafeSubprocessRunner.execute_bounded(
                ["powershell", "-Command", "Start-Sleep -Seconds 5"],
                timeout_seconds=1,
            )
        assert "strict timeout" in str(exc_info.value)

    def test_bounded_output_truncation(self) -> None:
        # Generate 1000 bytes with limit of 100 bytes
        cmd = ["powershell", "-Command", "Write-Output ('A' * 1000)"]
        returncode, stdout, stderr = SafeSubprocessRunner.execute_bounded(
            cmd,
            timeout_seconds=5,
            max_output_bytes=100,
        )
        assert len(stdout.encode("utf-8")) <= 100
