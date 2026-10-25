"""
ExifTool forensic metadata extraction adapter.

Integrates Phil Harvey's ExifTool CLI via sandboxed subprocess execution:
- Extracts full EXIF, IPTC, XMP, MakerNotes, and container headers into structured JSON.
- Uses '--' argument isolation to eliminate flag injection attacks.
- Enforces strict execution timeouts and output bounding.
- Maps raw tags to normalized forensic fields with missing fields marked as 'Unavailable'.
- Embeds courtroom disclaimer regarding metadata reproducibility and lack of proof of authenticity.
"""

from __future__ import annotations

import json
import logging
import os
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

logger = logging.getLogger("ps05.forensics.exiftool")

FORENSIC_AUTHENTICITY_DISCLAIMER = (
    "FORENSIC METADATA NOTICE: Consistent, standard, or normal-looking EXIF metadata can be "
    "readily injected, stripped, cloned, or altered using standard tools and hex editors. "
    "Normal metadata demonstrates technical container attributes but DOES NOT prove historical authenticity, "
    "camera provenance, or absence of tampering prior to intake."
)


class ExifToolAdapter(BaseMetadataAdapter):
    """Adapter for Phil Harvey's ExifTool utility."""

    def __init__(
        self,
        binary_path: str = "exiftool",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(binary_path, timeout_seconds)

    @property
    def tool_name(self) -> str:
        return "ExifTool"

    def resolve_binary(self) -> str:
        """Locate exiftool binary across PATH and platform-specific standard paths."""
        # 1. Directly specified valid path
        if self.binary_path and Path(self.binary_path).is_file():
            return str(Path(self.binary_path).resolve())

        # 2. Check system PATH
        for candidate in ("exiftool", "exiftool.exe", "ExifTool.exe"):
            found = shutil.which(candidate)
            if found:
                return str(Path(found).resolve())

        # 3. Windows standard installation locations
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            win_candidates = [
                Path(local_app_data) / "Programs" / "ExifTool" / "ExifTool.exe",
                Path(local_app_data) / "Programs" / "ExifTool" / "exiftool.exe",
            ]
            for win_cand in win_candidates:
                if win_cand.is_file():
                    return str(win_cand.resolve())

        program_files = os.environ.get("ProgramFiles", "")
        if program_files:
            win_pf = Path(program_files) / "exiftool" / "exiftool.exe"
            if win_pf.is_file():
                return str(win_pf.resolve())

        # 4. Linux standard paths
        for nix_path in (Path("/usr/bin/exiftool"), Path("/usr/local/bin/exiftool")):
            if nix_path.is_file():
                return str(nix_path)

        raise ForensicExecutionError(
            f"ExifTool executable ('{self.binary_path}') was not found. "
            "Ensure ExifTool is installed on the host or inside the container."
        )

    def query_version(self) -> str:
        """Query tool version via 'exiftool -ver'."""
        binary = self.resolve_binary()
        returncode, stdout, stderr = SafeSubprocessRunner.execute_bounded(
            [binary, "-ver"],
            timeout_seconds=5,
        )
        if returncode == 0 and stdout.strip():
            return stdout.strip().splitlines()[0]
        raise ForensicExecutionError(f"Failed to query ExifTool version: {stderr.strip() or stdout.strip()}")

    def build_command(self, file_path: Path) -> list[str]:
        """
        Construct subprocess argument list with '--' flag separation.
        """
        binary = self.resolve_binary()
        return [
            binary,
            "-json",
            "-G",  # Group names prefix (e.g. EXIF:Make, File:ImageWidth)
            "-a",  # Allow duplicate tag names across groups
            "-u",  # Extract unknown tags
            "-charset",
            "filename=UTF8",
            "--",  # Strict flag terminator: prevents filename from being evaluated as CLI flags
            str(file_path),
        ]

    def extract_metadata(self, file_path: Path) -> ToolExecutionResult:
        """
        Run ExifTool against target file and return structured, sanitized metadata.
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
                # ExifTool often logs warnings or minor tag format notices to stderr
                errors.extend([line for line in stderr.splitlines() if line.strip()])

            raw_dict: dict[str, Any] = {}
            if stdout.strip():
                try:
                    parsed = json.loads(stdout)
                    if isinstance(parsed, list) and len(parsed) > 0:
                        raw_dict = parsed[0]
                    elif isinstance(parsed, dict):
                        raw_dict = parsed
                except json.JSONDecodeError as jde:
                    errors.append(f"Failed to decode ExifTool JSON output: {jde}")

            success = (returncode == 0 or bool(raw_dict)) and not (returncode != 0 and not raw_dict)

            # Standardize and filter forensic metadata
            filtered_metadata = self._normalize_metadata(raw_dict)

            provenance = {
                "file_sha256_at_extraction": file_sha256,
                "file_size_bytes": file_size,
                "command_invoked": [cmd[0], "-json", "-G", "-a", "-u", "--", Path(file_path).name],
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
            logger.exception("ExifTool extraction failed: %s", exc)
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
                    "forensic_authenticity_notice": FORENSIC_AUTHENTICITY_DISCLAIMER,
                },
                provenance={
                    "file_sha256_at_extraction": file_sha256,
                    "file_size_bytes": file_size,
                },
            )

    def _normalize_metadata(self, raw: dict[str, Any]) -> dict[str, Any]:
        """
        Map nested ExifTool tags to a predictable, robust forensic schema.
        Missing fields are explicitly represented as 'Unavailable' or None.
        """
        def find_tag(*candidates: str) -> Any:
            """Return first matching tag from raw metadata, or None."""
            for tag in candidates:
                if tag in raw and raw[tag] is not None and str(raw[tag]).strip() != "":
                    return raw[tag]
                # Also try without group prefix
                for k, v in raw.items():
                    if k.split(":")[-1].lower() == tag.split(":")[-1].lower() and v is not None:
                        return v
            return None

        # Dimensions & Format
        width = find_tag("File:ImageWidth", "EXIF:ExifImageWidth", "Composite:ImageWidth")
        height = find_tag("File:ImageHeight", "EXIF:ExifImageHeight", "Composite:ImageHeight")

        try:
            width_val = int(width) if width is not None else None
        except (ValueError, TypeError):
            width_val = None

        try:
            height_val = int(height) if height is not None else None
        except (ValueError, TypeError):
            height_val = None

        if width_val and height_val:
            dimensions_str = f"{width_val}x{height_val}"
            aspect_ratio_str = self._calc_aspect_ratio(width_val, height_val)
        else:
            dimensions_str = "Unavailable"
            aspect_ratio_str = "Unavailable"

        # Megapixels
        megapixels = find_tag("Composite:Megapixels")
        if megapixels is None and width_val and height_val:
            megapixels = round((width_val * height_val) / 1_000_000.0, 2)

        # Timestamps
        timestamps = {
            "date_time_original": find_tag("EXIF:DateTimeOriginal") or "Unavailable",
            "create_date": find_tag("EXIF:CreateDate", "QuickTime:CreateDate") or "Unavailable",
            "modify_date": find_tag("EXIF:ModifyDate", "QuickTime:ModifyDate") or "Unavailable",
            "file_modify_date": find_tag("File:FileModifyDate") or "Unavailable",
        }

        # Software & Device tags
        software_tags = {
            "make": find_tag("EXIF:Make") or "Unavailable",
            "model": find_tag("EXIF:Model") or "Unavailable",
            "software": find_tag("EXIF:Software") or "Unavailable",
            "lens_model": find_tag("EXIF:LensModel", "Composite:LensID") or "Unavailable",
            "artist": find_tag("EXIF:Artist") or "Unavailable",
            "copyright": find_tag("EXIF:Copyright") or "Unavailable",
            "serial_number": find_tag("EXIF:SerialNumber", "EXIF:BodySerialNumber") or "Unavailable",
        }

        # Camera Capture Parameters
        camera_settings = {
            "iso": find_tag("EXIF:ISO") or "Unavailable",
            "f_number": find_tag("EXIF:FNumber") or "Unavailable",
            "exposure_time": find_tag("EXIF:ExposureTime") or "Unavailable",
            "focal_length": find_tag("EXIF:FocalLength") or "Unavailable",
            "flash": find_tag("EXIF:Flash") or "Unavailable",
            "exposure_program": find_tag("EXIF:ExposureProgram") or "Unavailable",
            "metering_mode": find_tag("EXIF:MeteringMode") or "Unavailable",
        }

        # Geolocation
        lat = find_tag("Composite:GPSLatitude", "EXIF:GPSLatitude")
        lon = find_tag("Composite:GPSLongitude", "EXIF:GPSLongitude")
        alt = find_tag("Composite:GPSAltitude", "EXIF:GPSAltitude")

        gps = {
            "latitude": str(lat) if lat is not None else "Unavailable",
            "longitude": str(lon) if lon is not None else "Unavailable",
            "altitude": str(alt) if alt is not None else "Unavailable",
        }

        return {
            "file_type": find_tag("File:FileType", "File:FileTypeExtension") or "Unavailable",
            "mime_type": find_tag("File:MIMEType") or "Unavailable",
            "image_width": width_val if width_val is not None else "Unavailable",
            "image_height": height_val if height_val is not None else "Unavailable",
            "dimensions": dimensions_str,
            "aspect_ratio": aspect_ratio_str,
            "megapixels": megapixels if megapixels is not None else "Unavailable",
            "color_space": find_tag("EXIF:ColorSpace", "ICC_Profile:ProfileDescription") or "Unavailable",
            "bits_per_sample": find_tag("File:BitsPerSample") or "Unavailable",
            "timestamps": timestamps,
            "software_tags": software_tags,
            "camera_settings": camera_settings,
            "gps": gps,
            "total_tags_extracted": len(raw),
            "forensic_authenticity_notice": FORENSIC_AUTHENTICITY_DISCLAIMER,
        }

    @staticmethod
    def _calc_aspect_ratio(w: int, h: int) -> str:
        """Calculate simplified aspect ratio string (e.g. 16:9, 4:3, 1:1)."""
        import math
        gcd = math.gcd(w, h)
        if gcd > 0:
            sw = w // gcd
            sh = h // gcd
            # Check for common standard aspect ratios
            if (sw, sh) in {(16, 9), (4, 3), (3, 2), (1, 1), (9, 16), (21, 9)}:
                return f"{sw}:{sh}"
            # Approximate decimal ratio
            ratio = round(w / h, 2)
            return f"{ratio}:1 ({sw}:{sh})"
        return "Unavailable"
