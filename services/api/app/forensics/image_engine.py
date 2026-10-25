"""
Image forensic analysis engine using Pillow, OpenCV, and NumPy.

Forensic Invariants:
1. NEVER modify the original evidentiary bitstream. Read-only inspection only.
2. Recompress ONLY a separate in-memory or scratch JPEG analysis copy using a documented quality setting.
3. Record exact execution metadata: quality setting, amplification factor, tool versions, and timestamps.
4. Mark ELA as not applicable for non-JPEG formats (e.g., PNG, WEBP, GIF, TIFF).
5. Strictly adhere to forensic standards: DO NOT label a file manipulated solely because a heatmap
   region appears bright (high frequency edges, text, and fine textures naturally compress with
   higher error levels in authentic images).
"""

from __future__ import annotations

import io
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import PIL
from PIL import Image

from app.db.models.finding import FindingSeverity, FindingType
from app.storage.hasher import MultiHasher

logger = logging.getLogger("ps05.forensics.image_engine")

ENGINE_VERSION = "1.0.0"
DEFAULT_ELA_QUALITY = 95
DEFAULT_AMPLIFICATION_SCALE = 15.0

# Supported JPEG formats for ELA
JPEG_FORMATS = {"JPEG", "JPG", "MPO"}


@dataclass
class ImageProperties:
    """Forensic geometric and color properties of an image."""

    format: str
    mime_type: str
    width: int
    height: int
    dimensions: str
    aspect_ratio: str
    aspect_ratio_float: float
    color_mode: str
    channels: int
    color_depth_bits: int
    has_alpha: bool
    is_animated: bool
    opencv_shape: list[int]
    opencv_dtype: str
    mean_intensity_per_channel: list[float]
    std_intensity_per_channel: list[float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HashIntegrityResult:
    """Result of intake hash verification against stored bytes."""

    intake_hash_sha256: str
    current_hash_sha256: str
    is_intact: bool
    bytes_verified: int
    verified_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ELAResult:
    """Error Level Analysis output and statistics."""

    is_applicable: bool
    inapplicability_reason: str | None
    recompression_quality: int | None
    amplification_scale: float | None
    mean_error: float | None
    std_error: float | None
    max_error: float | None
    min_error: float | None
    high_disparity_ratio: float | None
    heatmap_bytes: bytes | None = field(default=None, repr=False)
    heatmap_filename: str | None = None
    heatmap_mime_type: str | None = None
    heatmap_sha256: str | None = None
    heatmap_size_bytes: int | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("heatmap_bytes", None)
        return d


@dataclass
class StructuredFinding:
    """Structured forensic finding adhering to database schema."""

    finding_type: str
    severity: str
    title: str
    description: str
    confidence_score: float
    evidence_offset: str | None = None
    finding_metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ImageAnalysisResult:
    """Comprehensive image analysis result envelope."""

    properties: ImageProperties
    hash_integrity: HashIntegrityResult
    ela: ELAResult
    findings: list[StructuredFinding]
    limitations: list[str]
    execution_duration_ms: float
    completed_at: str

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "image_properties": self.properties.to_dict(),
            "hash_integrity": self.hash_integrity.to_dict(),
            "ela": self.ela.to_dict(),
            "findings_count": len(self.findings),
            "limitations": self.limitations,
            "execution_duration_ms": self.execution_duration_ms,
            "completed_at": self.completed_at,
            "engine_version": ENGINE_VERSION,
            "pillow_version": PIL.__version__,
            "opencv_version": cv2.__version__,
            "numpy_version": np.__version__,
        }


class ImageForensicsEngine:
    """
    Forensic image analyzer enforcing strict read-only guarantees on evidentiary media.
    """

    def __init__(
        self,
        default_quality: int = DEFAULT_ELA_QUALITY,
        default_scale: float = DEFAULT_AMPLIFICATION_SCALE,
    ) -> None:
        self.default_quality = default_quality
        self.default_scale = default_scale

    def inspect_properties(self, file_path: Path, raw_bytes: bytes) -> ImageProperties:
        """
        Inspect physical image properties using Pillow and OpenCV.
        Does not alter the source bitstream.
        """
        # 1. Pillow Inspection
        with Image.open(io.BytesIO(raw_bytes)) as pil_img:
            img_format = (pil_img.format or "UNKNOWN").upper()
            width, height = pil_img.size
            color_mode = pil_img.mode
            is_animated = getattr(pil_img, "is_animated", False)

            # Determine channels and depth
            channel_count = len(pil_img.getbands()) if hasattr(pil_img, "getbands") else 1
            has_alpha = "A" in color_mode or "transparency" in pil_img.info

            # Bits per channel
            if color_mode in ("1", "L", "P"):
                bits_per_channel = 8 if color_mode != "1" else 1
            elif color_mode in ("RGB", "YCbCr"):
                bits_per_channel = 8
            elif color_mode in ("RGBA", "CMYK"):
                bits_per_channel = 8
            elif color_mode.startswith("I;16"):
                bits_per_channel = 16
            else:
                bits_per_channel = 8
            total_depth_bits = bits_per_channel * channel_count

            # Aspect ratio string
            gcd = math.gcd(width, height)
            if gcd > 0:
                aspect_ratio = f"{width // gcd}:{height // gcd}"
            else:
                aspect_ratio = f"{width}:{height}"
            aspect_ratio_float = round(width / max(height, 1), 4)

            mime_type = Image.MIME.get(img_format, f"image/{img_format.lower()}")

        # 2. OpenCV Matrix Inspection
        cv_arr = cv2.imdecode(np.frombuffer(raw_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if cv_arr is not None:
            cv_shape = list(cv_arr.shape)
            cv_dtype = str(cv_arr.dtype)

            # Intensity stats per channel
            if len(cv_arr.shape) == 2:
                # Grayscale
                mean_intensity = [round(float(np.mean(cv_arr)), 2)]
                std_intensity = [round(float(np.std(cv_arr)), 2)]
            elif len(cv_arr.shape) == 3:
                channels = cv_arr.shape[2]
                mean_intensity = [
                    round(float(np.mean(cv_arr[:, :, i])), 2) for i in range(channels)
                ]
                std_intensity = [
                    round(float(np.std(cv_arr[:, :, i])), 2) for i in range(channels)
                ]
            else:
                mean_intensity = [round(float(np.mean(cv_arr)), 2)]
                std_intensity = [round(float(np.std(cv_arr)), 2)]
        else:
            cv_shape = [height, width, channel_count]
            cv_dtype = "uint8"
            mean_intensity = [0.0] * channel_count
            std_intensity = [0.0] * channel_count

        return ImageProperties(
            format=img_format,
            mime_type=mime_type,
            width=width,
            height=height,
            dimensions=f"{width}x{height}",
            aspect_ratio=aspect_ratio,
            aspect_ratio_float=aspect_ratio_float,
            color_mode=color_mode,
            channels=channel_count,
            color_depth_bits=total_depth_bits,
            has_alpha=has_alpha,
            is_animated=is_animated,
            opencv_shape=cv_shape,
            opencv_dtype=cv_dtype,
            mean_intensity_per_channel=mean_intensity,
            std_intensity_per_channel=std_intensity,
        )

    def perform_ela(
        self,
        raw_bytes: bytes,
        img_format: str,
        quality: int | None = None,
        scale: float | None = None,
        evidence_number: str = "EVIDENCE",
    ) -> ELAResult:
        """
        Execute Error Level Analysis (ELA) with strict non-destructive constraints.

        Invariants:
        - NEVER write to or modify the original bitstream.
        - Recompress strictly to an isolated in-memory buffer using Pillow.
        - Mark ELA as not applicable for non-JPEG formats.
        - Generate a separate colorized ELA heatmap artifact.
        """
        effective_quality = quality if quality is not None else self.default_quality
        effective_scale = scale if scale is not None else self.default_scale
        now = datetime.now(UTC)

        provenance = {
            "engine_version": ENGINE_VERSION,
            "pillow_version": PIL.__version__,
            "opencv_version": cv2.__version__,
            "numpy_version": np.__version__,
            "executed_at": now.isoformat(),
            "recompression_quality_setting": effective_quality,
            "amplification_scale_factor": effective_scale,
        }

        # Check if format is a supported JPEG
        if img_format.upper() not in JPEG_FORMATS:
            logger.info("ELA marked not applicable: format '%s' is non-JPEG", img_format)
            return ELAResult(
                is_applicable=False,
                inapplicability_reason=(
                    f"Error Level Analysis (ELA) is mathematically defined for lossy Discrete Cosine "
                    f"Transform (DCT) 8x8 block quantization in JPEG images. The target format "
                    f"'{img_format}' does not utilize JPEG DCT compression; ELA is therefore not applicable."
                ),
                recompression_quality=None,
                amplification_scale=None,
                mean_error=None,
                std_error=None,
                max_error=None,
                min_error=None,
                high_disparity_ratio=None,
                heatmap_bytes=None,
                provenance=provenance,
            )

        # Non-destructive in-memory recompression
        with Image.open(io.BytesIO(raw_bytes)) as original_img:
            # Ensure RGB mode for standardized DCT compression
            if original_img.mode != "RGB":
                rgb_original = original_img.convert("RGB")
            else:
                rgb_original = original_img.copy()

            # Recompress ONLY the temporary copy into an in-memory buffer
            recompressed_buffer = io.BytesIO()
            rgb_original.save(
                recompressed_buffer,
                format="JPEG",
                quality=effective_quality,
                optimize=False,
            )
            recompressed_bytes = recompressed_buffer.getvalue()

        # Re-read recompressed copy
        with Image.open(io.BytesIO(recompressed_bytes)) as recompressed_img:
            recompressed_rgb = recompressed_img.convert("RGB")

            # Convert both to NumPy float arrays for high-precision difference computation
            orig_arr = np.array(rgb_original, dtype=np.float32)
            recomp_arr = np.array(recompressed_rgb, dtype=np.float32)

            # Compute absolute error per channel
            diff_arr = np.abs(orig_arr - recomp_arr)

            # Amplification: scale difference to reveal subtle compression discrepancies
            amplified_diff = np.clip(diff_arr * effective_scale, 0, 255).astype(np.uint8)

            # Overall single-channel error matrix for statistical analysis
            error_per_pixel = np.mean(diff_arr, axis=2)  # 2D array of pixel error
            mean_error = float(np.mean(error_per_pixel))
            std_error = float(np.std(error_per_pixel))
            max_error = float(np.max(error_per_pixel))
            min_error = float(np.min(error_per_pixel))

            # Disparity ratio: percentage of pixels with error exceeding 2 standard deviations above mean
            high_threshold = max(mean_error + 2.0 * std_error, 8.0)
            high_disparity_count = int(np.count_nonzero(error_per_pixel > high_threshold))
            high_disparity_ratio = float(high_disparity_count / max(error_per_pixel.size, 1))

            # Generate ELA Heatmap Artifact using OpenCV COLORMAP_JET
            # Convert amplified difference to grayscale for colormap mapping
            diff_gray = cv2.cvtColor(amplified_diff, cv2.COLOR_RGB2GRAY)

            # Normalize to 0-255 for vibrant color heatmap visualization
            min_val = float(diff_gray.min())
            max_val = float(diff_gray.max())
            if max_val > min_val:
                diff_norm = ((diff_gray.astype(np.float32) - min_val) / (max_val - min_val) * 255.0).astype(np.uint8)
            else:
                diff_norm = diff_gray

            heatmap_bgr = cv2.applyColorMap(diff_norm, cv2.COLORMAP_JET)

            # Encode separate heatmap artifact as PNG
            success, heatmap_png = cv2.imencode(".png", heatmap_bgr)
            if not success:
                raise RuntimeError("Failed to encode ELA heatmap artifact to PNG")

            heatmap_bytes = heatmap_png.tobytes()
            heatmap_sha256 = MultiHasher().hash_bytes(heatmap_bytes).sha256
            clean_number = "".join(c for c in evidence_number if c.isalnum() or c in "-_")
            heatmap_filename = f"ela_heatmap_{clean_number}_{now.strftime('%Y%m%d_%H%M%S')}.png"

            return ELAResult(
                is_applicable=True,
                inapplicability_reason=None,
                recompression_quality=effective_quality,
                amplification_scale=effective_scale,
                mean_error=round(mean_error, 4),
                std_error=round(std_error, 4),
                max_error=round(max_error, 4),
                min_error=round(min_error, 4),
                high_disparity_ratio=round(high_disparity_ratio, 4),
                heatmap_bytes=heatmap_bytes,
                heatmap_filename=heatmap_filename,
                heatmap_mime_type="image/png",
                heatmap_sha256=heatmap_sha256,
                heatmap_size_bytes=len(heatmap_bytes),
                provenance=provenance,
            )

    def generate_findings_and_limitations(
        self,
        properties: ImageProperties,
        hash_integrity: HashIntegrityResult,
        ela: ELAResult,
    ) -> tuple[list[StructuredFinding], list[str]]:
        """
        Produce structured forensic findings and legal limitations.

        Core Forensic Rule:
        Do NOT label a file manipulated solely because a heatmap region appears bright.
        """
        findings: list[StructuredFinding] = []
        limitations: list[str] = [
            (
                "High ELA brightness does NOT prove forgery: Regions of high contrast, sharp boundaries, "
                "fine textures, and typographic text inherently generate higher DCT quantization error and "
                "naturally display as bright zones in authentic, unmanipulated JPEGs."
            ),
            (
                "Low ELA brightness does NOT prove authenticity: Flat, uniform regions (such as clear sky "
                "or solid studio backdrops) undergo minimal quantization error and naturally appear dark "
                "regardless of whether the content was spliced or genuine."
            ),
            (
                "Multi-generation resave degradation: Successive JPEG saves equalize error levels across "
                "the frame, progressively attenuating distinct error level boundaries."
            ),
            (
                "Independent corroboration required: ELA observations must be cross-verified against camera "
                "quantization tables, EXIF metadata consistency, and independent chain of custody."
            ),
        ]

        # 1. Cryptographic Hash Finding
        if hash_integrity.is_intact:
            findings.append(
                StructuredFinding(
                    finding_type=FindingType.OTHER.value,
                    severity=FindingSeverity.INFO.value,
                    title="Cryptographic Baseline Verified Intact",
                    description=(
                        f"Stored vault byte stream SHA-256 ({hash_integrity.current_hash_sha256}) "
                        f"matches the authoritative intake hash baseline with 100% bit-level precision. "
                        f"Verified {hash_integrity.bytes_verified:,} bytes."
                    ),
                    confidence_score=1.0,
                    evidence_offset="0x00000000",
                    finding_metadata={
                        "intake_hash": hash_integrity.intake_hash_sha256,
                        "current_hash": hash_integrity.current_hash_sha256,
                        "bytes_verified": hash_integrity.bytes_verified,
                    },
                )
            )
        else:
            findings.append(
                StructuredFinding(
                    finding_type=FindingType.HASH_TAMPER.value,
                    severity=FindingSeverity.CRITICAL.value,
                    title="Evidentiary Hash Mismatch (Tamper Detected)",
                    description=(
                        f"CRITICAL: Stored vault bytes yield SHA-256 {hash_integrity.current_hash_sha256}, "
                        f"which diverges from intake baseline {hash_integrity.intake_hash_sha256}."
                    ),
                    confidence_score=1.0,
                    evidence_offset="0x00000000",
                    finding_metadata={
                        "expected_hash": hash_integrity.intake_hash_sha256,
                        "calculated_hash": hash_integrity.current_hash_sha256,
                    },
                )
            )

        # 2. Image Geometric & Color Properties Finding
        findings.append(
            StructuredFinding(
                finding_type=FindingType.OTHER.value,
                severity=FindingSeverity.INFO.value,
                title="Image Technical Properties Profiled",
                description=(
                    f"Image format: {properties.format} ({properties.mime_type}), "
                    f"dimensions: {properties.dimensions} ({properties.aspect_ratio}), "
                    f"color mode: {properties.color_mode} with {properties.channels} channels "
                    f"({properties.color_depth_bits}-bit total depth)."
                ),
                confidence_score=1.0,
                finding_metadata=properties.to_dict(),
            )
        )

        # 3. ELA Finding
        if not ela.is_applicable:
            findings.append(
                StructuredFinding(
                    finding_type=FindingType.OTHER.value,
                    severity=FindingSeverity.INFO.value,
                    title=f"ELA Not Applicable for Format '{properties.format}'",
                    description=(
                        ela.inapplicability_reason
                        or "Error Level Analysis is only applicable to lossy JPEG bitstreams."
                    ),
                    confidence_score=1.0,
                    finding_metadata={
                        "format": properties.format,
                        "is_applicable": False,
                    },
                )
            )
        else:
            # ELA applicable: assess error level distribution objectively without false accusations
            mean_err = ela.mean_error or 0.0
            std_err = ela.std_error or 0.0
            disparity_ratio = ela.high_disparity_ratio or 0.0

            # Determine objective severity classification
            if disparity_ratio > 0.15 and std_err > 12.0:
                severity = FindingSeverity.MEDIUM.value
                obs_summary = (
                    f"Noticeable error level variance observed across image regions "
                    f"(mean error: {mean_err:.2f}, std dev: {std_err:.2f}, "
                    f"high disparity ratio: {disparity_ratio * 100:.1f}%). "
                    f"Localized regions exhibit elevated recompression error relative to the baseline. "
                    f"Forensic Notice: This variation may stem from authentic high-contrast edges or "
                    f"compositional elements; manual visual inspection of the ELA heatmap artifact is required."
                )
            elif disparity_ratio > 0.05 or std_err > 6.0:
                severity = FindingSeverity.LOW.value
                obs_summary = (
                    f"Moderate compression error distribution (mean error: {mean_err:.2f}, "
                    f"std dev: {std_err:.2f}, high disparity ratio: {disparity_ratio * 100:.1f}%). "
                    f"Error levels are largely consistent with standard JPEG quantization along structural edges."
                )
            else:
                severity = FindingSeverity.INFO.value
                obs_summary = (
                    f"Uniform compression error distribution across the image "
                    f"(mean error: {mean_err:.2f}, std dev: {std_err:.2f}, "
                    f"high disparity ratio: {disparity_ratio * 100:.1f}%). "
                    f"No anomalous localized compression disparity detected."
                )

            findings.append(
                StructuredFinding(
                    finding_type=FindingType.ELA_DISPARITY.value,
                    severity=severity,
                    title="JPEG Error Level Analysis Completed",
                    description=obs_summary,
                    confidence_score=0.90,
                    finding_metadata={
                        "recompression_quality": ela.recompression_quality,
                        "amplification_scale": ela.amplification_scale,
                        "mean_error": ela.mean_error,
                        "std_error": ela.std_error,
                        "max_error": ela.max_error,
                        "min_error": ela.min_error,
                        "high_disparity_ratio": ela.high_disparity_ratio,
                        "heatmap_sha256": ela.heatmap_sha256,
                        "forensic_caution": (
                            "Do not interpret bright heatmap areas as manipulation without corroborating metadata."
                        ),
                    },
                )
            )

        return findings, limitations

    def analyze_file(
        self,
        file_path: Path,
        expected_sha256: str,
        quality: int | None = None,
        scale: float | None = None,
        evidence_number: str = "EVIDENCE",
    ) -> ImageAnalysisResult:
        """
        Execute full image forensic workflow on a local file path.
        Guarantees that the original file is NEVER modified.
        """
        start_time = time.perf_counter()

        if not file_path.is_file():
            raise FileNotFoundError(f"Evidentiary image file not found: {file_path}")

        # Record hash of original before opening
        pre_sha256 = MultiHasher().hash_file(file_path).sha256

        # Read bytes in read-only mode
        with open(file_path, "rb") as f:
            raw_bytes = f.read()

        # Re-verify hash of read bytes
        intake_match = (pre_sha256.lower() == expected_sha256.lower())
        hash_integrity = HashIntegrityResult(
            intake_hash_sha256=expected_sha256.lower(),
            current_hash_sha256=pre_sha256.lower(),
            is_intact=intake_match,
            bytes_verified=len(raw_bytes),
            verified_at=datetime.now(UTC).isoformat(),
        )

        # 1. Properties
        properties = self.inspect_properties(file_path, raw_bytes)

        # 2. ELA
        ela = self.perform_ela(
            raw_bytes=raw_bytes,
            img_format=properties.format,
            quality=quality,
            scale=scale,
            evidence_number=evidence_number,
        )

        # 3. Findings and Limitations
        findings, limitations = self.generate_findings_and_limitations(
            properties=properties,
            hash_integrity=hash_integrity,
            ela=ela,
        )

        # Guarantee: Verify that file on disk is completely unchanged
        post_sha256 = MultiHasher().hash_file(file_path).sha256
        if post_sha256 != pre_sha256:
            raise RuntimeError(
                f"FATAL FORENSIC INTEGRITY VIOLATION: File '{file_path}' was modified during analysis! "
                f"Original SHA-256: {pre_sha256}, Post-analysis SHA-256: {post_sha256}"
            )

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        completed_at = datetime.now(UTC).isoformat()

        return ImageAnalysisResult(
            properties=properties,
            hash_integrity=hash_integrity,
            ela=ela,
            findings=findings,
            limitations=limitations,
            execution_duration_ms=duration_ms,
            completed_at=completed_at,
        )
