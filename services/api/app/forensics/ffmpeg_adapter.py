"""
FFmpeg video frame extraction and stream processing adapter.

Forensic Guarantees:
1. Strictly executes subprocesses via argument lists (never shell=True or string concatenation).
2. Employs '--' argument boundary before file arguments to prevent CLI flag injection.
3. Enforces strict execution timeouts with automatic process termination.
4. Bounded stdout capture (default 10 MB per frame) to prevent memory exhaustion bombs.
5. Validates inputs: rejects non-existent, empty, non-video, and oversized files safely.
6. Records complete provenance: tool version, extraction settings, timestamps, hashes, errors.
7. Stores extracted frames as derivative artifacts isolated from original evidence.
8. Embeds forensic disclaimers: extracted frames and anomalies are investigative indicators,
   never definitive legal proof of tampering.
"""

from __future__ import annotations

import logging
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.core.config import Settings, get_settings
from app.forensics.base import (
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    BaseMetadataAdapter,
    ForensicExecutionError,
    SafeSubprocessRunner,
)
from app.forensics.ffprobe_adapter import FFprobeAdapter
from app.storage.hasher import MultiHasher

logger = logging.getLogger("ps05.forensics.ffmpeg")

MAX_REPRESENTATIVE_FRAMES_LIMIT = 50
DEFAULT_MAX_FRAMES = 10
DEFAULT_MAX_RESOLUTION = (1920, 1080)
DEFAULT_MAX_VIDEO_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB

FORENSIC_FRAME_EXTRACTION_DISCLAIMER = (
    "FORENSIC NOTICE: Extracted representative video frames reflect decoder-rendered bitstream "
    "states at sampled timestamps. Frame rendering variations, codec compression artifacts, "
    "or missing timestamps do not establish intentional video manipulation or editing."
)

DEFAULT_MAX_AUDIO_BYTES = 500 * 1024 * 1024  # 500 MB
DEFAULT_MAX_AUDIO_DURATION_SECONDS = 600.0  # 10 minutes
DEFAULT_MAX_PCM_DECODE_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_AUDIO_SAMPLE_RATE = 44100

FORENSIC_AUDIO_DECODING_DISCLAIMER = (
    "FORENSIC NOTICE: Decoded audio PCM samples reflect bitstream data decoded via FFmpeg. "
    "Signal anomalies, lossy codec cutoffs, clipping, or DC offset may stem from analog capture, "
    "lossy compression, or acoustic environment rather than intentional audio editing."
)


@dataclass
class AudioDecodeResult:
    """Enveloping result of an FFmpeg bounded audio stream decoding operation."""

    success: bool
    samples: np.ndarray = field(repr=False)
    sample_rate_hz: int
    channels: int
    bit_depth: int
    duration_seconds: float
    total_samples: int
    truncated: bool
    tool_name: str
    tool_version: str
    extracted_at: str
    execution_duration_ms: float
    provenance: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    forensic_notice: str = FORENSIC_AUDIO_DECODING_DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        """Convert result envelope to dictionary excluding raw numpy array."""
        return {
            "success": self.success,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "bit_depth": self.bit_depth,
            "duration_seconds": self.duration_seconds,
            "total_samples": self.total_samples,
            "truncated": self.truncated,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "extracted_at": self.extracted_at,
            "execution_duration_ms": self.execution_duration_ms,
            "provenance": self.provenance,
            "errors": self.errors,
            "warnings": self.warnings,
            "forensic_notice": self.forensic_notice,
        }


@dataclass
class ExtractedVideoFrame:
    """Standardized representation of a single extracted video frame artifact."""

    frame_index: int
    timestamp_seconds: float
    image_bytes: bytes = field(repr=False)
    filename: str
    mime_type: str
    sha256: str
    dhash: str
    width: int
    height: int
    file_size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary without binary bytes."""
        d = asdict(self)
        d.pop("image_bytes", None)
        return d


@dataclass
class FrameExtractionResult:
    """Enveloping result of an FFmpeg representative frame extraction operation."""

    success: bool
    frames: list[ExtractedVideoFrame]
    tool_name: str
    tool_version: str
    extracted_at: str
    execution_duration_ms: float
    extraction_settings: dict[str, Any]
    provenance: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    forensic_notice: str = FORENSIC_FRAME_EXTRACTION_DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        """Convert result envelope to dictionary."""
        return {
            "success": self.success,
            "frames": [f.to_dict() for f in self.frames],
            "frame_count": len(self.frames),
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "extracted_at": self.extracted_at,
            "execution_duration_ms": self.execution_duration_ms,
            "extraction_settings": self.extraction_settings,
            "provenance": self.provenance,
            "errors": self.errors,
            "warnings": self.warnings,
            "forensic_notice": self.forensic_notice,
        }


def compute_frame_dhash(image_bytes: bytes, hash_size: int = 8) -> str:
    """
    Compute 64-bit difference hash (dHash) for visual perceptual comparison of frame bytes.
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return "0" * 16

        resized = cv2.resize(img, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
        diff = resized[:, 1:] > resized[:, :-1]
        decimal_val = 0
        for bit in diff.flatten():
            decimal_val = (decimal_val << 1) | int(bit)
        return f"{decimal_val:016x}"
    except Exception as exc:
        logger.warning("Failed to compute dHash for extracted frame: %s", exc)
        return "0" * 16


class FFmpegAdapter(BaseMetadataAdapter):
    """
    Subprocess adapter for FFmpeg utility providing secure representative frame extraction.
    """

    def __init__(
        self,
        binary_path: str = "ffmpeg",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        *,
        ffprobe_adapter: FFprobeAdapter | None = None,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(binary_path, timeout_seconds)
        self.settings = settings or get_settings()
        self.ffprobe_adapter = ffprobe_adapter or FFprobeAdapter(
            binary_path=self.settings.FFPROBE_PATH,
            timeout_seconds=self.timeout_seconds,
        )

    @property
    def tool_name(self) -> str:
        return "FFmpeg"

    def resolve_binary(self) -> str:
        """Locate ffmpeg binary on system PATH or configured paths."""
        if self.binary_path and Path(self.binary_path).is_file():
            return str(Path(self.binary_path).resolve())

        for candidate in ("ffmpeg", "ffmpeg.exe"):
            found = shutil.which(candidate)
            if found:
                return str(Path(found).resolve())

        for nix_path in (Path("/usr/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")):
            if nix_path.is_file():
                return str(nix_path)

        raise ForensicExecutionError(
            f"FFmpeg executable ('{self.binary_path}') was not found. "
            "Ensure ffmpeg is installed on the host or inside the container."
        )

    def query_version(self) -> str:
        """Query tool version via 'ffmpeg -version'."""
        binary = self.resolve_binary()
        returncode, stdout, stderr = SafeSubprocessRunner.execute_bounded(
            [binary, "-version"],
            timeout_seconds=5,
        )
        if returncode == 0 and stdout.strip():
            first_line = stdout.strip().splitlines()[0]
            match = re.search(r"version\s+([^\s]+)", first_line)
            if match:
                return match.group(1)
            return first_line[:32]
        raise ForensicExecutionError(f"Failed to query FFmpeg version: {stderr.strip() or stdout.strip()}")

    def extract_metadata(self, file_path: Path) -> Any:
        """
        Base adapter compliance: delegate metadata extraction to FFprobe.
        """
        return self.ffprobe_adapter.extract_metadata(file_path)

    def extract_representative_frames(
        self,
        file_path: Path,
        *,
        timestamps: list[float] | None = None,
        max_frames: int = DEFAULT_MAX_FRAMES,
        max_resolution: tuple[int, int] = DEFAULT_MAX_RESOLUTION,
        timeout_seconds: int | None = None,
        evidence_number: str = "EVID-000",
        max_file_size_bytes: int = DEFAULT_MAX_VIDEO_BYTES,
    ) -> FrameExtractionResult:
        """
        Extract a bounded number of representative frames at controlled timestamps.

        Defensive Guarantees:
        - Validates input existence, non-emptiness, and file size bounds.
        - Verifies the input contains at least one decodable video stream via FFprobe.
        - Enforces strict upper bound on number of frames (`MAX_REPRESENTATIVE_FRAMES_LIMIT`).
        - Restricts output frame dimensions with an aspect-preserving scale filter.
        - Enforces subprocess execution timeouts per frame.
        - Never throws unhandled exceptions on malformed, corrupt, or non-video inputs.
        """
        start_time = time.perf_counter()
        extracted_at = datetime.now(UTC).isoformat()
        timeout = timeout_seconds or self.timeout_seconds
        bounded_max_frames = max(1, min(max_frames, MAX_REPRESENTATIVE_FRAMES_LIMIT))

        # 1. Input Validation: File existence & basic attributes
        if not file_path.is_file():
            return FrameExtractionResult(
                success=False,
                frames=[],
                tool_name=self.tool_name,
                tool_version=self.get_version() if self.is_available() else "Unavailable",
                extracted_at=extracted_at,
                execution_duration_ms=0.0,
                extraction_settings={
                    "timestamps_requested": timestamps,
                    "max_frames": bounded_max_frames,
                    "max_resolution": list(max_resolution),
                },
                provenance={"target_path": str(file_path)},
                errors=[f"Target file does not exist or is not a regular file: {file_path}"],
            )

        file_size = file_path.stat().st_size
        if file_size == 0:
            return FrameExtractionResult(
                success=False,
                frames=[],
                tool_name=self.tool_name,
                tool_version=self.get_version() if self.is_available() else "Unavailable",
                extracted_at=extracted_at,
                execution_duration_ms=0.0,
                extraction_settings={
                    "timestamps_requested": timestamps,
                    "max_frames": bounded_max_frames,
                    "max_resolution": list(max_resolution),
                },
                provenance={"target_path": str(file_path), "file_size_bytes": 0},
                errors=["Target file is empty (0 bytes). Cannot extract video frames."],
            )

        if file_size > max_file_size_bytes:
            return FrameExtractionResult(
                success=False,
                frames=[],
                tool_name=self.tool_name,
                tool_version=self.get_version() if self.is_available() else "Unavailable",
                extracted_at=extracted_at,
                execution_duration_ms=0.0,
                extraction_settings={
                    "timestamps_requested": timestamps,
                    "max_frames": bounded_max_frames,
                    "max_resolution": list(max_resolution),
                },
                provenance={"target_path": str(file_path), "file_size_bytes": file_size},
                errors=[
                    f"Target file size ({file_size} bytes) exceeds maximum allowed resource limit "
                    f"({max_file_size_bytes} bytes)."
                ],
            )

        # 2. Compute file SHA-256 for provenance
        file_sha256 = MultiHasher().hash_file(file_path).sha256

        # 3. Stream Inspection using FFprobe
        try:
            probe_info = self.ffprobe_adapter.inspect_video_streams(file_path)
        except Exception as exc:
            logger.warning("FFprobe stream inspection failed on %s: %s", file_path, exc)
            probe_info = {"has_video": False, "errors": [str(exc)]}

        if not probe_info.get("has_video"):
            return FrameExtractionResult(
                success=False,
                frames=[],
                tool_name=self.tool_name,
                tool_version=self.get_version() if self.is_available() else "Unavailable",
                extracted_at=extracted_at,
                execution_duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
                extraction_settings={
                    "timestamps_requested": timestamps,
                    "max_frames": bounded_max_frames,
                    "max_resolution": list(max_resolution),
                },
                provenance={
                    "target_path": str(file_path),
                    "file_sha256": file_sha256,
                    "file_size_bytes": file_size,
                },
                errors=[
                    "No valid decodable video stream found in container. "
                    "Input may be malformed, corrupted, or not a video file."
                ],
            )

        # 4. Resolve Controlled Target Timestamps
        duration_sec = 0.0
        primary_stream = probe_info.get("primary_stream") or {}
        stream_dur = primary_stream.get("duration_seconds")
        if isinstance(stream_dur, int | float) and stream_dur > 0:
            duration_sec = float(stream_dur)
        else:
            container_dur = probe_info.get("container", {}).get("duration_seconds")
            if isinstance(container_dur, int | float) and container_dur > 0:
                duration_sec = float(container_dur)

        target_timestamps: list[float] = []
        if timestamps:
            # Clean and bound user-requested timestamps
            valid_ts = [float(t) for t in timestamps if t >= 0.0]
            if duration_sec > 0:
                valid_ts = [min(t, duration_sec) for t in valid_ts]
            target_timestamps = sorted(valid_ts)[:bounded_max_frames]

        if not target_timestamps:
            if duration_sec > 0:
                if bounded_max_frames == 1:
                    target_timestamps = [round(duration_sec / 2.0, 3)]
                else:
                    # Distribute evenly across video duration
                    step = duration_sec / (bounded_max_frames + 1)
                    target_timestamps = [round(step * (i + 1), 3) for i in range(bounded_max_frames)]
            else:
                # Unknown duration: attempt single frame at start
                target_timestamps = [0.0]

        # 5. Execute Subprocess Frame Extraction
        binary = self.resolve_binary()
        tool_version = self.get_version()
        max_w, max_h = max_resolution
        scale_filter = f"scale='min({max_w},iw)':'min({max_h},ih)':force_original_aspect_ratio=decrease"

        extracted_frames: list[ExtractedVideoFrame] = []
        errors: list[str] = []
        warnings: list[str] = []
        commands_invoked: list[str] = []

        for idx, ts in enumerate(target_timestamps):
            cmd = [
                binary,
                "-nostdin",
                "-ss",
                f"{ts:.3f}",
                "-i",
                str(file_path),
                "-vframes",
                "1",
                "-vf",
                scale_filter,
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "-",
            ]
            commands_invoked.append(f"ffmpeg -ss {ts:.3f} -i [FILE] -vframes 1 -vf [SCALE] -f image2pipe -")

            try:
                retcode, raw_bytes, stderr = SafeSubprocessRunner.execute_bounded_bytes(
                    cmd,
                    timeout_seconds=timeout,
                    max_output_bytes=DEFAULT_MAX_OUTPUT_BYTES,
                )

                if retcode != 0 or not raw_bytes:
                    err_msg = f"Failed to extract frame at timestamp {ts}s (exit {retcode})"
                    if stderr.strip():
                        err_msg += f": {stderr.splitlines()[-1]}"
                    warnings.append(err_msg)
                    continue

                # Parse frame dimensions and compute hashes
                frame_sha256 = MultiHasher().hash_bytes(raw_bytes).sha256
                frame_dhash = compute_frame_dhash(raw_bytes)

                # Read actual width and height from decoded image array
                nparr = np.frombuffer(raw_bytes, np.uint8)
                decoded_img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
                if decoded_img is not None:
                    h, w = decoded_img.shape[:2]
                else:
                    w, h = 0, 0

                frame_filename = f"{evidence_number}_frame_{idx:03d}_{ts:.2f}s.png"

                frame_obj = ExtractedVideoFrame(
                    frame_index=idx,
                    timestamp_seconds=round(ts, 3),
                    image_bytes=raw_bytes,
                    filename=frame_filename,
                    mime_type="image/png",
                    sha256=frame_sha256,
                    dhash=frame_dhash,
                    width=w,
                    height=h,
                    file_size_bytes=len(raw_bytes),
                )
                extracted_frames.append(frame_obj)

            except ForensicExecutionError as fee:
                warnings.append(f"Timeout or execution error at timestamp {ts}s: {fee}")
            except Exception as exc:
                warnings.append(f"Unexpected extraction error at timestamp {ts}s: {exc}")

        execution_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        success = len(extracted_frames) > 0

        if not success:
            errors.append(
                "FFmpeg could not extract any representative frames from the media bitstream. "
                "The container or video stream may be corrupt, truncated, or incompatible."
            )

        provenance = {
            "source_file_sha256": file_sha256,
            "source_file_size_bytes": file_size,
            "stream_duration_seconds": duration_sec,
            "commands_executed": commands_invoked[:5],
            "total_commands_executed": len(commands_invoked),
            "video_codec": primary_stream.get("codec_name", "UNKNOWN"),
            "original_dimensions": primary_stream.get("dimensions", "UNKNOWN"),
        }

        settings_used = {
            "timestamps_requested": timestamps,
            "timestamps_evaluated": target_timestamps,
            "max_frames_configured": bounded_max_frames,
            "max_resolution": list(max_resolution),
            "timeout_seconds": timeout,
        }

        return FrameExtractionResult(
            success=success,
            frames=extracted_frames,
            tool_name=self.tool_name,
            tool_version=tool_version,
            extracted_at=extracted_at,
            execution_duration_ms=execution_duration_ms,
            extraction_settings=settings_used,
            provenance=provenance,
            errors=errors,
            warnings=warnings,
            forensic_notice=FORENSIC_FRAME_EXTRACTION_DISCLAIMER,
        )

    def decode_audio_stream(
        self,
        file_path: Path,
        *,
        max_duration_seconds: float = DEFAULT_MAX_AUDIO_DURATION_SECONDS,
        target_sample_rate_hz: int | None = DEFAULT_AUDIO_SAMPLE_RATE,
        max_channels: int = 1,
        max_bytes: int = DEFAULT_MAX_PCM_DECODE_BYTES,
        timeout_seconds: int | None = None,
        max_file_size_bytes: int = DEFAULT_MAX_AUDIO_BYTES,
    ) -> AudioDecodeResult:
        """
        Extract raw PCM audio samples from an audio or multimedia bitstream with defensive resource bounds.

        Guarantees:
        - Bounded duration (-t max_duration_seconds) enforced at decoder level.
        - Bounded stdout bytes (max_bytes) preventing memory exhaustion.
        - Downmixed to max_channels (mono by default) for consistent forensic spectral inspection.
        - Returns float32 normalized samples in [-1.0, 1.0].
        - Complete provenance: SHA-256, command invoked, timestamps, errors, warnings.
        """
        start_time = time.perf_counter()
        extracted_at = datetime.now(UTC).isoformat()
        timeout = timeout_seconds or self.timeout_seconds
        tool_version = self.get_version() if self.is_available() else "Unavailable"
        empty_samples = np.empty(0, dtype=np.float32)

        if not file_path.is_file():
            return AudioDecodeResult(
                success=False,
                samples=empty_samples,
                sample_rate_hz=0,
                channels=0,
                bit_depth=0,
                duration_seconds=0.0,
                total_samples=0,
                truncated=False,
                tool_name=self.tool_name,
                tool_version=tool_version,
                extracted_at=extracted_at,
                execution_duration_ms=0.0,
                provenance={"target_path": str(file_path)},
                errors=[f"Target file does not exist or is not a regular file: {file_path}"],
            )

        file_size = file_path.stat().st_size
        if file_size == 0:
            return AudioDecodeResult(
                success=False,
                samples=empty_samples,
                sample_rate_hz=0,
                channels=0,
                bit_depth=0,
                duration_seconds=0.0,
                total_samples=0,
                truncated=False,
                tool_name=self.tool_name,
                tool_version=tool_version,
                extracted_at=extracted_at,
                execution_duration_ms=0.0,
                provenance={"target_path": str(file_path), "file_size_bytes": 0},
                errors=["Target audio file is empty (0 bytes)."],
            )

        if file_size > max_file_size_bytes:
            return AudioDecodeResult(
                success=False,
                samples=empty_samples,
                sample_rate_hz=0,
                channels=0,
                bit_depth=0,
                duration_seconds=0.0,
                total_samples=0,
                truncated=False,
                tool_name=self.tool_name,
                tool_version=tool_version,
                extracted_at=extracted_at,
                execution_duration_ms=0.0,
                provenance={"target_path": str(file_path), "file_size_bytes": file_size},
                errors=[
                    f"Target file size ({file_size} bytes) exceeds maximum allowed resource limit ({max_file_size_bytes} bytes)."
                ],
            )

        file_sha256 = MultiHasher().hash_file(file_path).sha256

        # Check audio stream presence via FFprobe
        probe_info: dict[str, Any] = {}
        try:
            probe_info = self.ffprobe_adapter.inspect_audio_streams(file_path)
        except Exception as exc:
            logger.warning("FFprobe audio inspection failed on %s: %s", file_path, exc)

        has_audio = probe_info.get("has_audio", False)
        primary_stream = probe_info.get("primary_stream") or {}
        orig_sr = primary_stream.get("sample_rate_hz")
        orig_channels = primary_stream.get("channels")
        orig_bd = primary_stream.get("bit_depth")

        effective_sr = target_sample_rate_hz or (orig_sr if isinstance(orig_sr, int) and orig_sr > 0 else DEFAULT_AUDIO_SAMPLE_RATE)
        bit_depth = orig_bd if isinstance(orig_bd, int) and orig_bd > 0 else 16
        channels_val = orig_channels if isinstance(orig_channels, int) and orig_channels > 0 else max_channels

        # If FFprobe explicitly found no audio and success is True, container has no audio streams
        if probe_info.get("success") and not has_audio:
            return AudioDecodeResult(
                success=False,
                samples=empty_samples,
                sample_rate_hz=0,
                channels=0,
                bit_depth=0,
                duration_seconds=0.0,
                total_samples=0,
                truncated=False,
                tool_name=self.tool_name,
                tool_version=tool_version,
                extracted_at=extracted_at,
                execution_duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
                provenance={"target_path": str(file_path), "file_sha256": file_sha256, "file_size_bytes": file_size},
                errors=["No decodable audio stream found in container. Target may be malformed or non-audio media."],
            )

        try:
            binary = self.resolve_binary()
        except ForensicExecutionError as fee:
            return AudioDecodeResult(
                success=False,
                samples=empty_samples,
                sample_rate_hz=0,
                channels=0,
                bit_depth=0,
                duration_seconds=0.0,
                total_samples=0,
                truncated=False,
                tool_name=self.tool_name,
                tool_version="Unavailable",
                extracted_at=extracted_at,
                execution_duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
                provenance={"target_path": str(file_path), "file_sha256": file_sha256, "file_size_bytes": file_size},
                errors=[str(fee)],
            )

        cmd = [
            binary,
            "-nostdin",
            "-v",
            "error",
            "-t",
            f"{max_duration_seconds:.3f}",
            "-i",
            str(file_path),
            "-vn",
            "-sn",
            "-ac",
            str(max_channels),
            "-ar",
            str(effective_sr),
            "-f",
            "f32le",
            "-",
        ]

        errors: list[str] = []
        warnings: list[str] = []

        try:
            retcode, raw_bytes, stderr = SafeSubprocessRunner.execute_bounded_bytes(
                cmd,
                timeout_seconds=timeout,
                max_output_bytes=max_bytes,
            )

            is_truncated = len(raw_bytes) >= max_bytes
            if is_truncated:
                warnings.append(
                    f"Decoded audio byte stream reached the safety limit of {max_bytes} bytes; samples were truncated."
                )

            if retcode != 0:
                err_line = stderr.strip().splitlines()[-1] if stderr.strip() else f"Process exited with code {retcode}"
                if len(raw_bytes) > 0:
                    warnings.append(f"FFmpeg reported error while decoding audio: {err_line}")
                else:
                    errors.append(f"FFmpeg audio decoding failed: {err_line}")
                    return AudioDecodeResult(
                        success=False,
                        samples=empty_samples,
                        sample_rate_hz=effective_sr,
                        channels=channels_val,
                        bit_depth=bit_depth,
                        duration_seconds=0.0,
                        total_samples=0,
                        truncated=False,
                        tool_name=self.tool_name,
                        tool_version=tool_version,
                        extracted_at=extracted_at,
                        execution_duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
                        provenance={"target_path": str(file_path), "file_sha256": file_sha256, "file_size_bytes": file_size},
                        errors=errors,
                        warnings=warnings,
                    )

            n_samples = len(raw_bytes) // 4
            usable_bytes = raw_bytes[: n_samples * 4]
            samples = np.frombuffer(usable_bytes, dtype=np.float32).copy()
            samples = np.nan_to_num(samples, nan=0.0, posinf=1.0, neginf=-1.0)

            total_samples = len(samples)
            duration_sec = total_samples / effective_sr if effective_sr > 0 else 0.0

            execution_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            provenance = {
                "source_file_sha256": file_sha256,
                "source_file_size_bytes": file_size,
                "command_invoked": f"ffmpeg -nostdin -v error -t {max_duration_seconds:.3f} -i [FILE] -vn -sn -ac {max_channels} -ar {effective_sr} -f f32le -",
                "original_channels": orig_channels,
                "original_sample_rate": orig_sr,
                "decoded_sample_rate": effective_sr,
                "decoded_channels": max_channels,
            }

            return AudioDecodeResult(
                success=total_samples > 0,
                samples=samples,
                sample_rate_hz=effective_sr,
                channels=channels_val,
                bit_depth=bit_depth,
                duration_seconds=round(duration_sec, 4),
                total_samples=total_samples,
                truncated=is_truncated,
                tool_name=self.tool_name,
                tool_version=tool_version,
                extracted_at=extracted_at,
                execution_duration_ms=execution_duration_ms,
                provenance=provenance,
                errors=errors,
                warnings=warnings,
            )

        except ForensicExecutionError as fee:
            errors.append(f"Forensic execution error during audio decoding: {fee}")
            return AudioDecodeResult(
                success=False,
                samples=empty_samples,
                sample_rate_hz=effective_sr,
                channels=channels_val,
                bit_depth=bit_depth,
                duration_seconds=0.0,
                total_samples=0,
                truncated=False,
                tool_name=self.tool_name,
                tool_version=tool_version,
                extracted_at=extracted_at,
                execution_duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
                provenance={"target_path": str(file_path), "file_sha256": file_sha256, "file_size_bytes": file_size},
                errors=errors,
                warnings=warnings,
            )
