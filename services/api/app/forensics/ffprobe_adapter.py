"""
FFprobe multimedia container and stream analysis adapter.

Integrates FFprobe CLI via sandboxed subprocess execution:
- Extracts comprehensive container, stream, and codec data for audio and video media.
- Analyzes video dimensions, codecs, frame rates (with safe fractional arithmetic), pixel formats.
- Analyzes audio codecs, sample rates (Hz), channel counts, layouts, bit depths.
- Employs '--' argument boundary and non-shell subprocess execution.
- Maps output to a normalized forensic stream profile with missing fields marked as 'Unavailable'.
- Embeds courtroom disclaimer regarding container remuxing and metadata mutability.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.forensics.base import (
    DEFAULT_TIMEOUT_SECONDS,
    BaseMetadataAdapter,
    ForensicExecutionError,
    SafeSubprocessRunner,
    ToolExecutionResult,
)

logger = logging.getLogger("ps05.forensics.ffprobe")

FORENSIC_CONTAINER_DISCLAIMER = (
    "FORENSIC CONTAINER NOTICE: Multimedia container wrappers, codec declarations, and stream headers "
    "can be modified, re-multiplexed, or transcoded without altering perceptual content. "
    "A conforming container or standard stream layout DOES NOT establish historical authenticity, "
    "sensor provenance, or freedom from tampering prior to intake."
)


class FFprobeAdapter(BaseMetadataAdapter):
    """Adapter for FFprobe container and stream analysis utility."""

    def __init__(
        self,
        binary_path: str = "ffprobe",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(binary_path, timeout_seconds)

    @property
    def tool_name(self) -> str:
        return "FFprobe"

    def resolve_binary(self) -> str:
        """Locate ffprobe binary on system PATH or known paths."""
        if self.binary_path and Path(self.binary_path).is_file():
            return str(Path(self.binary_path).resolve())

        for candidate in ("ffprobe", "ffprobe.exe"):
            found = shutil.which(candidate)
            if found:
                return str(Path(found).resolve())

        # Check standard Linux paths
        for nix_path in (Path("/usr/bin/ffprobe"), Path("/usr/local/bin/ffprobe")):
            if nix_path.is_file():
                return str(nix_path)

        raise ForensicExecutionError(
            f"FFprobe executable ('{self.binary_path}') was not found. "
            "Ensure ffmpeg/ffprobe is installed on the host or inside the container."
        )

    def query_version(self) -> str:
        """Query tool version via 'ffprobe -version'."""
        binary = self.resolve_binary()
        returncode, stdout, stderr = SafeSubprocessRunner.execute_bounded(
            [binary, "-version"],
            timeout_seconds=5,
        )
        if returncode == 0 and stdout.strip():
            # First line is typically 'ffprobe version 8.1.1-full_build...'
            first_line = stdout.strip().splitlines()[0]
            match = re.search(r"version\s+([^\s]+)", first_line)
            if match:
                return match.group(1)
            return first_line[:32]
        raise ForensicExecutionError(f"Failed to query FFprobe version: {stderr.strip() or stdout.strip()}")

    def build_command(self, file_path: Path) -> list[str]:
        """
        Construct subprocess argument list with '--' flag separation.
        """
        binary = self.resolve_binary()
        return [
            binary,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            "--",  # Strict flag terminator
            str(file_path),
        ]

    def extract_metadata(self, file_path: Path) -> ToolExecutionResult:
        """
        Run FFprobe against media file and parse structured container and stream profiles.
        """
        start_time = time.perf_counter()
        extracted_at = datetime.now(UTC)
        errors: list[str] = []

        if not file_path.is_file():
            return ToolExecutionResult(
                tool_name=self.tool_name,
                tool_version=self.get_version(),
                extracted_at=extracted_at,
                execution_duration_ms=0.0,
                success=False,
                errors=[f"Target file does not exist or is not a regular file: {file_path}"],
                raw_metadata={},
                filtered_forensic_metadata={"status": "FILE_NOT_FOUND"},
                provenance={"target_path": str(file_path)},
            )

        file_sha256 = self.compute_file_sha256(file_path)
        file_size = file_path.stat().st_size

        try:
            cmd = self.build_command(file_path)
            tool_version = self.get_version()

            returncode, stdout, stderr = SafeSubprocessRunner.execute_bounded(
                cmd,
                timeout_seconds=self.timeout_seconds,
            )

            execution_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            if stderr.strip():
                errors.extend([line for line in stderr.splitlines() if line.strip()])

            raw_dict: dict[str, Any] = {}
            if stdout.strip():
                try:
                    raw_dict = json.loads(stdout)
                except json.JSONDecodeError as jde:
                    errors.append(f"Failed to decode FFprobe JSON output: {jde}")

            success = returncode == 0 and bool(raw_dict)
            if not success and returncode != 0 and not errors:
                errors.append(f"FFprobe exited with non-zero status code: {returncode}")

            filtered_metadata = self._normalize_metadata(raw_dict)

            provenance = {
                "file_sha256_at_extraction": file_sha256,
                "file_size_bytes": file_size,
                "command_invoked": [cmd[0], "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", "--", Path(file_path).name],
                "return_code": returncode,
            }

            return ToolExecutionResult(
                tool_name=self.tool_name,
                tool_version=tool_version,
                extracted_at=extracted_at,
                execution_duration_ms=execution_duration_ms,
                success=success,
                errors=errors,
                raw_metadata=raw_dict,
                filtered_forensic_metadata=filtered_metadata,
                provenance=provenance,
            )

        except Exception as exc:
            execution_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.exception("FFprobe extraction failed: %s", exc)
            return ToolExecutionResult(
                tool_name=self.tool_name,
                tool_version=self._cached_version or "Unavailable",
                extracted_at=extracted_at,
                execution_duration_ms=execution_duration_ms,
                success=False,
                errors=[str(exc)],
                raw_metadata={},
                filtered_forensic_metadata={
                    "status": "EXTRACTION_FAILED",
                    "error": str(exc),
                    "forensic_authenticity_notice": FORENSIC_CONTAINER_DISCLAIMER,
                },
                provenance={
                    "file_sha256_at_extraction": file_sha256,
                    "file_size_bytes": file_size,
                },
            )

    def _normalize_metadata(self, raw: dict[str, Any]) -> dict[str, Any]:
        """
        Normalize FFprobe JSON output into container, video streams, and audio streams.
        Missing values are explicitly recorded as 'Unavailable' or None.
        """
        fmt = raw.get("format", {})
        streams = raw.get("streams", [])

        # 1. Container normalization
        duration_sec: float | str = "Unavailable"
        if "duration" in fmt and fmt["duration"] is not None:
            try:
                duration_sec = round(float(fmt["duration"]), 4)
            except (ValueError, TypeError):
                duration_sec = "Unavailable"

        duration_formatted = self._format_duration(duration_sec) if isinstance(duration_sec, int | float) else "Unavailable"

        bitrate_bps: int | str = "Unavailable"
        if "bit_rate" in fmt and fmt["bit_rate"] is not None:
            try:
                bitrate_bps = int(fmt["bit_rate"])
            except (ValueError, TypeError):
                bitrate_bps = "Unavailable"

        size_bytes: int | str = "Unavailable"
        if "size" in fmt and fmt["size"] is not None:
            try:
                size_bytes = int(fmt["size"])
            except (ValueError, TypeError):
                size_bytes = "Unavailable"

        container_info = {
            "format_name": fmt.get("format_name") or "Unavailable",
            "format_long_name": fmt.get("format_long_name") or "Unavailable",
            "duration_seconds": duration_sec,
            "duration_formatted": duration_formatted,
            "bitrate_bps": bitrate_bps,
            "size_bytes": size_bytes,
            "stream_count": len(streams),
            "tags": fmt.get("tags", {}),
        }

        # 2. Streams classification
        video_streams: list[dict[str, Any]] = []
        audio_streams: list[dict[str, Any]] = []
        other_streams: list[dict[str, Any]] = []

        for s in streams:
            codec_type = s.get("codec_type", "").lower()
            if codec_type == "video":
                v_stream = self._normalize_video_stream(s)
                video_streams.append(v_stream)
            elif codec_type == "audio":
                a_stream = self._normalize_audio_stream(s)
                audio_streams.append(a_stream)
            else:
                other_streams.append({
                    "stream_index": s.get("index", 0),
                    "codec_type": codec_type or "Unavailable",
                    "codec_name": s.get("codec_name") or "Unavailable",
                })

        return {
            "container": container_info,
            "video_streams": video_streams,
            "audio_streams": audio_streams,
            "video_stream_count": len(video_streams),
            "audio_stream_count": len(audio_streams),
            "other_stream_count": len(other_streams),
            "forensic_authenticity_notice": FORENSIC_CONTAINER_DISCLAIMER,
        }

    def _normalize_video_stream(self, s: dict[str, Any]) -> dict[str, Any]:
        """Normalize video stream properties."""
        width = s.get("width")
        height = s.get("height")

        try:
            w_val = int(width) if width is not None else None
        except (ValueError, TypeError):
            w_val = None

        try:
            h_val = int(height) if height is not None else None
        except (ValueError, TypeError):
            h_val = None

        dimensions = f"{w_val}x{h_val}" if w_val and h_val else "Unavailable"
        aspect_ratio = s.get("display_aspect_ratio") or s.get("sample_aspect_ratio") or "Unavailable"

        # Frame rate parsing
        fps_val = self._parse_frame_rate(s.get("r_frame_rate")) or self._parse_frame_rate(s.get("avg_frame_rate"))
        frame_rate_str = f"{fps_val:.2f} fps" if fps_val is not None else "Unavailable"

        # Bitrate
        v_bitrate: int | str = "Unavailable"
        if "bit_rate" in s and s["bit_rate"] is not None:
            try:
                v_bitrate = int(s["bit_rate"])
            except (ValueError, TypeError):
                v_bitrate = "Unavailable"

        # Duration
        v_duration: float | str = "Unavailable"
        if "duration" in s and s["duration"] is not None:
            try:
                v_duration = round(float(s["duration"]), 4)
            except (ValueError, TypeError):
                v_duration = "Unavailable"

        # Number of frames
        nb_frames: int | str = "Unavailable"
        if "nb_frames" in s and s["nb_frames"] is not None:
            try:
                nb_frames = int(s["nb_frames"])
            except (ValueError, TypeError):
                nb_frames = "Unavailable"

        # Timestamps
        start_time_val: float | str = "Unavailable"
        if "start_time" in s and s["start_time"] is not None:
            try:
                start_time_val = round(float(s["start_time"]), 4)
            except (ValueError, TypeError):
                start_time_val = "Unavailable"

        start_pts_val: int | str = "Unavailable"
        if "start_pts" in s and s["start_pts"] is not None:
            try:
                start_pts_val = int(s["start_pts"])
            except (ValueError, TypeError):
                start_pts_val = "Unavailable"

        return {
            "stream_index": s.get("index", 0),
            "codec_name": s.get("codec_name") or "Unavailable",
            "codec_long_name": s.get("codec_long_name") or "Unavailable",
            "profile": s.get("profile") or "Unavailable",
            "width": w_val if w_val is not None else "Unavailable",
            "height": h_val if h_val is not None else "Unavailable",
            "dimensions": dimensions,
            "display_aspect_ratio": aspect_ratio,
            "pixel_format": s.get("pix_fmt") or "Unavailable",
            "frame_rate": frame_rate_str,
            "duration_seconds": v_duration,
            "bitrate_bps": v_bitrate,
            "frame_count": nb_frames,
            "color_space": s.get("color_space") or "Unavailable",
            "color_range": s.get("color_range") or "Unavailable",
            "start_time_seconds": start_time_val,
            "start_pts": start_pts_val,
            "time_base": s.get("time_base") or "Unavailable",
            "tags": s.get("tags", {}),
            "disposition": s.get("disposition", {}),
        }

    def inspect_video_streams(self, file_path: Path) -> dict[str, Any]:
        """
        Focused inspection of video streams extracting duration, codec,
        dimensions, frame rate, timestamps, and available stream metadata.
        """
        result = self.extract_metadata(file_path)
        metadata = result.filtered_forensic_metadata
        video_streams = metadata.get("video_streams", [])
        container = metadata.get("container", {})

        return {
            "success": result.success,
            "tool_name": result.tool_name,
            "tool_version": result.tool_version,
            "file_sha256": result.provenance.get("file_sha256_at_extraction", ""),
            "container": container,
            "video_streams": video_streams,
            "primary_stream": video_streams[0] if video_streams else None,
            "has_video": len(video_streams) > 0,
            "errors": result.errors,
            "forensic_authenticity_notice": metadata.get("forensic_authenticity_notice", FORENSIC_CONTAINER_DISCLAIMER),
        }

    def _normalize_audio_stream(self, s: dict[str, Any]) -> dict[str, Any]:
        """Normalize audio stream properties."""
        sample_rate: int | str = "Unavailable"
        if "sample_rate" in s and s["sample_rate"] is not None:
            try:
                sample_rate = int(s["sample_rate"])
            except (ValueError, TypeError):
                sample_rate = "Unavailable"

        channels: int | str = "Unavailable"
        if "channels" in s and s["channels"] is not None:
            try:
                channels = int(s["channels"])
            except (ValueError, TypeError):
                channels = "Unavailable"

        a_bitrate: int | str = "Unavailable"
        if "bit_rate" in s and s["bit_rate"] is not None:
            try:
                a_bitrate = int(s["bit_rate"])
            except (ValueError, TypeError):
                a_bitrate = "Unavailable"

        a_duration: float | str = "Unavailable"
        if "duration" in s and s["duration"] is not None:
            try:
                a_duration = round(float(s["duration"]), 4)
            except (ValueError, TypeError):
                a_duration = "Unavailable"

        # Bit depth
        bit_depth: int | str = "Unavailable"
        for key in ("bits_per_raw_sample", "bits_per_sample"):
            if key in s and s[key] is not None:
                try:
                    bd_val = int(s[key])
                    if bd_val > 0:
                        bit_depth = bd_val
                        break
                except (ValueError, TypeError):
                    pass
        if bit_depth == "Unavailable":
            sample_fmt = str(s.get("sample_fmt") or "").lower()
            if sample_fmt in ("s16", "s16p"):
                bit_depth = 16
            elif sample_fmt in ("s32", "s32p", "flt", "fltp"):
                bit_depth = 32
            elif sample_fmt in ("u8", "u8p"):
                bit_depth = 8
            elif sample_fmt in ("s24", "s24p"):
                bit_depth = 24
            elif sample_fmt in ("dbl", "dblp"):
                bit_depth = 64

        # Timestamps
        start_time_val: float | str = "Unavailable"
        if "start_time" in s and s["start_time"] is not None:
            try:
                start_time_val = round(float(s["start_time"]), 4)
            except (ValueError, TypeError):
                start_time_val = "Unavailable"

        start_pts_val: int | str = "Unavailable"
        if "start_pts" in s and s["start_pts"] is not None:
            try:
                start_pts_val = int(s["start_pts"])
            except (ValueError, TypeError):
                start_pts_val = "Unavailable"

        return {
            "stream_index": s.get("index", 0),
            "codec_name": s.get("codec_name") or "Unavailable",
            "codec_long_name": s.get("codec_long_name") or "Unavailable",
            "profile": s.get("profile") or "Unavailable",
            "sample_rate_hz": sample_rate,
            "channels": channels,
            "channel_layout": s.get("channel_layout") or "Unavailable",
            "sample_format": s.get("sample_fmt") or "Unavailable",
            "bit_depth": bit_depth,
            "bitrate_bps": a_bitrate,
            "duration_seconds": a_duration,
            "start_time_seconds": start_time_val,
            "start_pts": start_pts_val,
            "time_base": s.get("time_base") or "Unavailable",
            "tags": s.get("tags", {}),
            "disposition": s.get("disposition", {}),
        }

    def inspect_audio_streams(self, file_path: Path) -> dict[str, Any]:
        """
        Focused inspection of audio streams extracting duration, codec,
        sample rate, channels, bit depth, timestamps, and stream metadata.
        """
        result = self.extract_metadata(file_path)
        metadata = result.filtered_forensic_metadata
        audio_streams = metadata.get("audio_streams", [])
        container = metadata.get("container", {})

        return {
            "success": result.success,
            "tool_name": result.tool_name,
            "tool_version": result.tool_version,
            "file_sha256": result.provenance.get("file_sha256_at_extraction", ""),
            "container": container,
            "audio_streams": audio_streams,
            "primary_stream": audio_streams[0] if audio_streams else None,
            "has_audio": len(audio_streams) > 0,
            "audio_stream_count": len(audio_streams),
            "errors": result.errors,
            "forensic_authenticity_notice": metadata.get("forensic_authenticity_notice", FORENSIC_CONTAINER_DISCLAIMER),
        }

    @staticmethod
    def _parse_frame_rate(rate_str: str | None) -> float | None:
        """Safely parse fractional frame rate string (e.g. '30/1' or '30000/1001') without eval."""
        if not rate_str or not isinstance(rate_str, str):
            return None
        rate_str = rate_str.strip()
        if "/" in rate_str:
            parts = rate_str.split("/")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                num = int(parts[0])
                den = int(parts[1])
                if den > 0 and num > 0:
                    return float(num / den)
        else:
            try:
                val = float(rate_str)
                if val > 0:
                    return val
            except ValueError:
                pass
        return None

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration into HH:MM:SS.ss."""
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = seconds % 60
        if hrs > 0:
            return f"{hrs:02d}:{mins:02d}:{secs:05.2f}"
        return f"{mins:02d}:{secs:05.2f}"
