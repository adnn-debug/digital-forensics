"""
Unit tests for ImageForensicsEngine.

Verifies:
- Physical image properties (format, dimensions, color mode, channels, depth).
- Non-destructive processing: original bitstream is NEVER modified (SHA-256 unchanged).
- JPEG Error Level Analysis (ELA) and separate heatmap artifact generation.
- Marking ELA as not applicable for non-JPEG formats (PNG, etc.).
- Deliberately modified vs. untouched JPEG error profiles.
- Strict adherence to rule: do not label manipulated solely on heatmap brightness.
- Intake hash verification (intact vs tampered).
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from app.db.models.finding import FindingSeverity, FindingType
from app.forensics.image_engine import ImageForensicsEngine
from app.storage.hasher import MultiHasher


def create_test_jpeg(
    path: Path,
    width: int = 320,
    height: int = 240,
    quality: int = 95,
) -> str:
    """Create a synthetic untouched JPEG and return its SHA-256."""
    img = Image.new("RGB", (width, height), color=(120, 150, 180))
    draw = ImageDraw.Draw(img)
    # Draw simple shapes
    draw.rectangle([40, 40, 120, 120], fill=(220, 100, 50), outline=(255, 255, 255))
    draw.ellipse([160, 60, 260, 180], fill=(50, 200, 100), outline=(0, 0, 0))

    img.save(path, format="JPEG", quality=quality)
    return MultiHasher().hash_file(path).sha256


def create_modified_jpeg(
    path: Path,
    width: int = 320,
    height: int = 240,
) -> str:
    """
    Create a deliberately modified JPEG:
    Base image saved at quality 70, then a high-contrast foreign patch is spliced in,
    and the final composite is saved at quality 95.
    This creates an intentional multi-compression disparity typical of image splicing.
    """
    base_img = Image.new("RGB", (width, height), color=(80, 90, 100))
    draw = ImageDraw.Draw(base_img)
    draw.rectangle([20, 20, 150, 150], fill=(150, 150, 150))

    # Save base at lower quality
    buf = io.BytesIO()
    base_img.save(buf, format="JPEG", quality=70)
    buf.seek(0)
    reopened = Image.open(buf).convert("RGB")

    # Splice a foreign uncompressed patch with high frequency noise into the reopened image
    patch_arr = np.random.randint(0, 255, (60, 60, 3), dtype=np.uint8)
    patch_img = Image.fromarray(patch_arr, mode="RGB")
    reopened.paste(patch_img, (180, 40))

    reopened.save(path, format="JPEG", quality=95)
    return MultiHasher().hash_file(path).sha256


def create_test_png(
    path: Path,
    width: int = 200,
    height: int = 150,
) -> str:
    """Create a synthetic PNG image and return its SHA-256."""
    img = Image.new("RGBA", (width, height), color=(40, 80, 120, 255))
    draw = ImageDraw.Draw(img)
    draw.line([(0, 0), (width, height)], fill=(255, 255, 0, 255), width=3)
    img.save(path, format="PNG")
    return MultiHasher().hash_file(path).sha256


class TestImageForensicsEngine:
    """Unit test suite for forensic image analyzer."""

    def test_untouched_jpeg_analysis(self, tmp_path: Path) -> None:
        """Verify properties, ELA execution, artifact generation, and zero alteration of original."""
        img_path = tmp_path / "untouched_sample.jpg"
        expected_sha256 = create_test_jpeg(img_path, width=320, height=240, quality=95)

        engine = ImageForensicsEngine(default_quality=95, default_scale=15.0)
        result = engine.analyze_file(
            file_path=img_path,
            expected_sha256=expected_sha256,
            evidence_number="EV-TEST-001",
        )

        # 1. Properties inspection
        assert result.properties.format == "JPEG"
        assert result.properties.width == 320
        assert result.properties.height == 240
        assert result.properties.dimensions == "320x240"
        assert result.properties.color_mode == "RGB"
        assert result.properties.channels == 3
        assert result.properties.color_depth_bits == 24
        assert result.properties.has_alpha is False
        assert result.properties.opencv_shape == [240, 320, 3]

        # 2. Hash integrity
        assert result.hash_integrity.is_intact is True
        assert result.hash_integrity.intake_hash_sha256 == expected_sha256
        assert result.hash_integrity.current_hash_sha256 == expected_sha256
        assert result.hash_integrity.bytes_verified > 0

        # 3. ELA result
        assert result.ela.is_applicable is True
        assert result.ela.recompression_quality == 95
        assert result.ela.amplification_scale == 15.0
        assert result.ela.mean_error is not None
        assert result.ela.std_error is not None
        assert result.ela.heatmap_bytes is not None
        assert len(result.ela.heatmap_bytes) > 0
        assert result.ela.heatmap_mime_type == "image/png"
        assert result.ela.heatmap_sha256 is not None
        assert "pillow_version" in result.ela.provenance
        assert "opencv_version" in result.ela.provenance
        assert "numpy_version" in result.ela.provenance

        # 4. Structured findings
        assert len(result.findings) >= 3
        # Check that none of the findings falsely label the file manipulated based on brightness
        for finding in result.findings:
            assert "forgery" not in finding.description.lower() or "not prove" in finding.description.lower()
            if finding.finding_type == FindingType.ELA_DISPARITY.value:
                assert finding.title == "JPEG Error Level Analysis Completed"

        # 5. Evidentiary limitations
        assert len(result.limitations) >= 3
        assert any("High ELA brightness does NOT prove forgery" in lim for lim in result.limitations)

        # 6. CRUCIAL FORENSIC INVARIANT: The original file on disk MUST NOT be modified
        current_sha256 = MultiHasher().hash_file(img_path).sha256
        assert current_sha256 == expected_sha256, "Original evidence file was modified!"

    def test_deliberately_modified_jpeg_analysis(self, tmp_path: Path) -> None:
        """Verify that deliberately modified/spliced JPEG produces ELA disparity observations."""
        img_path = tmp_path / "modified_spliced.jpg"
        expected_sha256 = create_modified_jpeg(img_path, width=320, height=240)

        engine = ImageForensicsEngine(default_quality=95, default_scale=15.0)
        result = engine.analyze_file(
            file_path=img_path,
            expected_sha256=expected_sha256,
            evidence_number="EV-TEST-002",
        )

        assert result.properties.format == "JPEG"
        assert result.ela.is_applicable is True
        assert result.ela.heatmap_bytes is not None
        assert result.ela.std_error is not None
        assert result.ela.max_error is not None
        assert result.ela.max_error > 0.0

        # Verify that original file remains 100% unchanged
        assert MultiHasher().hash_file(img_path).sha256 == expected_sha256

    def test_non_jpeg_format_marked_not_applicable(self, tmp_path: Path) -> None:
        """Verify that non-JPEG (PNG) image marks ELA as not applicable without errors."""
        img_path = tmp_path / "lossless_sample.png"
        expected_sha256 = create_test_png(img_path, width=200, height=150)

        engine = ImageForensicsEngine()
        result = engine.analyze_file(
            file_path=img_path,
            expected_sha256=expected_sha256,
            evidence_number="EV-TEST-003",
        )

        assert result.properties.format == "PNG"
        assert result.properties.has_alpha is True
        assert result.properties.channels == 4
        assert result.properties.color_mode == "RGBA"

        # ELA must be explicitly marked as not applicable
        assert result.ela.is_applicable is False
        assert result.ela.heatmap_bytes is None
        assert result.ela.inapplicability_reason is not None
        assert "PNG" in result.ela.inapplicability_reason

        # Finding must explain inapplicability
        ela_findings = [f for f in result.findings if "Not Applicable" in f.title]
        assert len(ela_findings) == 1
        assert ela_findings[0].severity == FindingSeverity.INFO.value

        # File on disk remains untouched
        assert MultiHasher().hash_file(img_path).sha256 == expected_sha256

    def test_tampered_hash_detection(self, tmp_path: Path) -> None:
        """Verify that if stored bytes diverge from intake baseline, HASH_TAMPER is flagged."""
        img_path = tmp_path / "tampered_sample.jpg"
        actual_sha256 = create_test_jpeg(img_path)
        bogus_intake_sha256 = "0" * 64

        engine = ImageForensicsEngine()
        result = engine.analyze_file(
            file_path=img_path,
            expected_sha256=bogus_intake_sha256,
            evidence_number="EV-TAMPER-001",
        )

        assert result.hash_integrity.is_intact is False
        assert result.hash_integrity.intake_hash_sha256 == bogus_intake_sha256
        assert result.hash_integrity.current_hash_sha256 == actual_sha256

        tamper_findings = [
            f for f in result.findings if f.finding_type == FindingType.HASH_TAMPER.value
        ]
        assert len(tamper_findings) == 1
        assert tamper_findings[0].severity == FindingSeverity.CRITICAL.value

        # Original file remains untouched
        assert MultiHasher().hash_file(img_path).sha256 == actual_sha256
