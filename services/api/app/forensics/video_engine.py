"""
Video forensic analysis engine using OpenCV and NumPy.

Forensic Invariants:
1. NEVER modify the original evidentiary bitstream. Read-only inspection only.
2. Verify SHA-256 bitstream integrity against expected intake hash prior to analysis.
3. Record exact execution metadata: codec fourcc, dimensions, frame rates, keyframe timestamps.
4. Extract intra-coded / representative scene keyframes and compute perceptual hashes (dHash).
5. Document forensic limitations: scene cuts and frame drops may stem from encoder rate control,
   network packet loss, or intentional editorial splicing.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.db.models.finding import FindingSeverity, FindingType
from app.forensics.image_engine import HashIntegrityResult, StructuredFinding
from app.storage.hasher import MultiHasher

logger = logging.getLogger("ps05.forensics.video_engine")

ENGINE_VERSION = "1.0.0"
MAX_KEYFRAMES_DEFAULT = 12
SCENE_DIFF_THRESHOLD = 30.0  # Mean absolute pixel difference threshold for scene change


@dataclass
class VideoContainerProperties:
    """Forensic container and stream properties of a video bitstream."""

    width: int
    height: int
    dimensions: str
    aspect_ratio: str
    aspect_ratio_float: float
    fps: float
    total_frames: int
    duration_seconds: float
    codec_fourcc: str
    is_valid_stream: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VideoKeyframe:
    """Extracted keyframe or scene boundary image artifact."""

    frame_index: int
    timestamp_seconds: float
    image_bytes: bytes = field(repr=False)
    filename: str
    mime_type: str
    sha256: str
    dhash: str
    width: int
    height: int
    is_scene_change: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("image_bytes", None)
        return d


@dataclass
class TemporalAnalysisMetrics:
    """Temporal and inter-frame disparity metrics."""

    scene_change_count: int
    scene_change_timestamps: list[float]
    frozen_frame_sequences_count: int
    average_frame_diff: float
    max_frame_diff: float
    keyframe_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VideoAnalysisResult:
    """Comprehensive video forensic analysis result envelope."""

    properties: VideoContainerProperties
    hash_integrity: HashIntegrityResult
    temporal_metrics: TemporalAnalysisMetrics
    keyframes: list[VideoKeyframe]
    findings: list[StructuredFinding]
    limitations: list[str]
    execution_duration_ms: float
    completed_at: str

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "container_properties": self.properties.to_dict(),
            "hash_integrity": self.hash_integrity.to_dict(),
            "temporal_metrics": self.temporal_metrics.to_dict(),
            "keyframes": [k.to_dict() for k in self.keyframes],
            "findings_count": len(self.findings),
            "limitations": self.limitations,
            "execution_duration_ms": self.execution_duration_ms,
            "completed_at": self.completed_at,
            "engine_version": ENGINE_VERSION,
            "opencv_version": cv2.__version__,
            "numpy_version": np.__version__,
        }


def compute_dhash(image_gray: np.ndarray, hash_size: int = 8) -> str:
    """
    Compute 64-bit difference hash (dHash) for visual perceptual comparison.

    Resizes image to (hash_size + 1, hash_size), computes row-wise gradient,
    and formats bits into hexadecimal string.
    """
    resized = cv2.resize(image_gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    decimal_val = 0
    for bit in diff.flatten():
        decimal_val = (decimal_val << 1) | int(bit)
    return f"{decimal_val:016x}"


class VideoForensicsEngine:
    """Engine executing temporal slicing, scene transition, and keyframe indexing."""

    def __init__(self, max_keyframes: int = MAX_KEYFRAMES_DEFAULT) -> None:
        self.max_keyframes = max_keyframes

    def analyze_file(
        self,
        file_path: Path,
        expected_sha256: str,
        evidence_number: str = "EVID-000",
        max_keyframes: int | None = None,
    ) -> VideoAnalysisResult:
        """Execute full video forensic workflow against local video file."""
        start_time = time.perf_counter()
        completed_at = datetime.now(UTC).isoformat()
        cap_max_keyframes = max_keyframes or self.max_keyframes

        if not file_path.is_file():
            raise FileNotFoundError(f"Video file not found: {file_path}")

        # 1. Verify Bitstream Hash Integrity
        multi_hasher = MultiHasher()
        hash_digests = multi_hasher.hash_file(file_path)
        is_intact = hash_digests.sha256.lower() == expected_sha256.lower()

        hash_integrity = HashIntegrityResult(
            intake_hash_sha256=expected_sha256,
            current_hash_sha256=hash_digests.sha256,
            is_intact=is_intact,
            bytes_verified=hash_digests.byte_count,
            verified_at=completed_at,
        )

        findings: list[StructuredFinding] = []
        limitations: list[str] = [
            "Scene boundary thresholds are heuristic; high-motion or strobe lighting may register false positive scene cuts.",
            "Variable frame rate (VFR) video can exhibit timestamp jitter that does not constitute malicious splicing.",
            "Compression artifacts and GOP structure are heavily codec-dependent and require contextual correlation with audio and metadata.",
        ]

        if not is_intact:
            findings.append(
                StructuredFinding(
                    finding_type=FindingType.HASH_TAMPER.value,
                    severity=FindingSeverity.CRITICAL.value,
                    title="Cryptographic Hash Mismatch Detected",
                    description=(
                        f"Stored video bitstream SHA-256 digest ({hash_digests.sha256}) differs from "
                        f"the intake baseline ({expected_sha256}). Possible file alteration or corruption."
                    ),
                    confidence_score=1.0,
                    evidence_offset="0x00000000",
                    finding_metadata={
                        "expected_sha256": expected_sha256,
                        "calculated_sha256": hash_digests.sha256,
                    },
                )
            )

        # 2. Open Video Capture
        cap = cv2.VideoCapture(str(file_path))
        if not cap.isOpened():
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            props = VideoContainerProperties(
                width=0,
                height=0,
                dimensions="0x0",
                aspect_ratio="N/A",
                aspect_ratio_float=0.0,
                fps=0.0,
                total_frames=0,
                duration_seconds=0.0,
                codec_fourcc="NONE",
                is_valid_stream=False,
            )
            findings.append(
                StructuredFinding(
                    finding_type=FindingType.CONTAINER_MISMATCH.value,
                    severity=FindingSeverity.HIGH.value,
                    title="Unreadable Video Stream Container",
                    description="OpenCV failed to demux or decode video stream from the container.",
                    confidence_score=0.9,
                )
            )
            metrics = TemporalAnalysisMetrics(
                scene_change_count=0,
                scene_change_timestamps=[],
                frozen_frame_sequences_count=0,
                average_frame_diff=0.0,
                max_frame_diff=0.0,
                keyframe_count=0,
            )
            return VideoAnalysisResult(
                properties=props,
                hash_integrity=hash_integrity,
                temporal_metrics=metrics,
                keyframes=[],
                findings=findings,
                limitations=limitations,
                execution_duration_ms=duration_ms,
                completed_at=completed_at,
            )

        # 3. Read Stream Metadata Properties
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        fourcc_str = "".join([chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)]).strip()

        duration_sec = (total_frames / fps) if fps > 0 and total_frames > 0 else 0.0
        ar_float = (width / height) if height > 0 else 0.0
        gcd = math.gcd(width, height) if width > 0 and height > 0 else 1
        aspect_ratio = f"{width // gcd}:{height // gcd}" if gcd > 0 else "N/A"

        props = VideoContainerProperties(
            width=width,
            height=height,
            dimensions=f"{width}x{height}",
            aspect_ratio=aspect_ratio,
            aspect_ratio_float=round(ar_float, 4),
            fps=round(fps, 3),
            total_frames=total_frames,
            duration_seconds=round(duration_sec, 3),
            codec_fourcc=fourcc_str or "UNKNOWN",
            is_valid_stream=True,
        )

        if fps <= 0 or total_frames <= 0:
            findings.append(
                StructuredFinding(
                    finding_type=FindingType.CONTAINER_MISMATCH.value,
                    severity=FindingSeverity.MEDIUM.value,
                    title="Anomalous Frame Header Statistics",
                    description=f"Container reported invalid FPS ({fps}) or frame count ({total_frames}).",
                    confidence_score=0.8,
                )
            )

        # 4. Temporal Analysis Loop & Keyframe Extraction
        keyframes: list[VideoKeyframe] = []
        scene_change_timestamps: list[float] = []
        frame_diffs: list[float] = []
        prev_gray: np.ndarray | None = None
        consecutive_frozen = 0
        frozen_sequences_count = 0

        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            current_timestamp = (frame_idx / fps) if fps > 0 else 0.0
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Scene Cut / Frame Difference detection
            is_scene_cut = False
            if prev_gray is not None:
                # Compute absolute frame difference
                diff = cv2.absdiff(gray, prev_gray)
                mean_diff = float(np.mean(diff))
                frame_diffs.append(mean_diff)

                if mean_diff < 0.1:
                    consecutive_frozen += 1
                else:
                    if consecutive_frozen >= 15:  # ~0.5 second of identical frames
                        frozen_sequences_count += 1
                    consecutive_frozen = 0

                if mean_diff >= SCENE_DIFF_THRESHOLD:
                    is_scene_cut = True
                    scene_change_timestamps.append(round(current_timestamp, 3))

            # Decide whether to extract this frame as a keyframe
            is_initial_frame = (frame_idx == 0)
            should_extract = is_initial_frame or is_scene_cut

            # Periodic keyframe selection if we don't have enough scene cuts
            if not should_extract and len(keyframes) < cap_max_keyframes:
                interval = max(1, total_frames // cap_max_keyframes) if total_frames > 0 else 30
                if frame_idx % interval == 0:
                    should_extract = True

            if should_extract and len(keyframes) < cap_max_keyframes:
                # Encode keyframe to PNG
                success, encoded_buf = cv2.imencode(".png", frame)
                if success:
                    raw_png = encoded_buf.tobytes()
                    dhash_val = compute_dhash(gray)
                    kf_sha256 = MultiHasher().hash_bytes(raw_png).sha256
                    kf_filename = f"{evidence_number}_keyframe_{frame_idx:05d}_{current_timestamp:.2f}s.png"

                    keyframe_obj = VideoKeyframe(
                        frame_index=frame_idx,
                        timestamp_seconds=round(current_timestamp, 3),
                        image_bytes=raw_png,
                        filename=kf_filename,
                        mime_type="image/png",
                        sha256=kf_sha256,
                        dhash=dhash_val,
                        width=width,
                        height=height,
                        is_scene_change=is_scene_cut,
                    )
                    keyframes.append(keyframe_obj)

            prev_gray = gray
            frame_idx += 1

            # Cap frame processing to protect against unbounded execution on giant files
            if frame_idx >= 5000:
                logger.warning("Video exceeds 5,000 frames; halting temporal loop for bounds protection.")
                break

        cap.release()

        # Handle final frozen sequence check
        if consecutive_frozen >= 15:
            frozen_sequences_count += 1

        avg_diff = float(np.mean(frame_diffs)) if frame_diffs else 0.0
        max_diff = float(np.max(frame_diffs)) if frame_diffs else 0.0

        metrics = TemporalAnalysisMetrics(
            scene_change_count=len(scene_change_timestamps),
            scene_change_timestamps=scene_change_timestamps,
            frozen_frame_sequences_count=frozen_sequences_count,
            average_frame_diff=round(avg_diff, 3),
            max_frame_diff=round(max_diff, 3),
            keyframe_count=len(keyframes),
        )

        # 5. Formulate Structured Findings
        if frozen_sequences_count > 0:
            findings.append(
                StructuredFinding(
                    finding_type=FindingType.KEYFRAME_INCONSISTENCY.value,
                    severity=FindingSeverity.LOW.value,
                    title="Frozen Frame Sequences Detected",
                    description=(
                        f"Detected {frozen_sequences_count} occurrence(s) of repeated static frames. "
                        "May indicate stream pause, camera freeze, or dropped frames."
                    ),
                    confidence_score=0.75,
                    finding_metadata={"frozen_sequences": frozen_sequences_count},
                )
            )

        if len(scene_change_timestamps) > 0:
            findings.append(
                StructuredFinding(
                    finding_type=FindingType.KEYFRAME_INCONSISTENCY.value,
                    severity=FindingSeverity.INFO.value,
                    title="Scene Boundary Transitions Identified",
                    description=(
                        f"Identified {len(scene_change_timestamps)} abrupt temporal transition(s) / scene cuts "
                        f"at timestamps: {scene_change_timestamps[:5]} (showing up to 5)."
                    ),
                    confidence_score=0.85,
                    finding_metadata={
                        "scene_count": len(scene_change_timestamps),
                        "timestamps": scene_change_timestamps,
                    },
                )
            )

        execution_duration_ms = (time.perf_counter() - start_time) * 1000.0

        return VideoAnalysisResult(
            properties=props,
            hash_integrity=hash_integrity,
            temporal_metrics=metrics,
            keyframes=keyframes,
            findings=findings,
            limitations=limitations,
            execution_duration_ms=round(execution_duration_ms, 2),
            completed_at=completed_at,
        )
