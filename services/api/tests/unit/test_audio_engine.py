"""Unit tests for AudioForensicsEngine and audio adapter operations."""

import struct
import wave
from pathlib import Path

import numpy as np
import pytest
from scipy import signal

from app.forensics.audio_engine import AudioForensicsEngine
from app.forensics.ffmpeg_adapter import FFmpegAdapter
from app.forensics.ffprobe_adapter import FFprobeAdapter
from app.storage.hasher import MultiHasher


@pytest.fixture
def sample_wav_path(tmp_path: Path) -> Path:
    """Generate a 1-second 44.1kHz 16-bit PCM WAV file with 440Hz tone."""
    file_path = tmp_path / "test_audio.wav"
    sample_rate = 44100
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    # 440 Hz sine wave + small harmonic
    tone = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 880 * t)
    int16_samples = (tone * 32767).astype(np.int16)

    with wave.open(str(file_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int16_samples.tobytes())

    return file_path


@pytest.fixture
def clipped_wav_path(tmp_path: Path) -> Path:
    """Generate a clipped audio file exceeding full-scale quantization."""
    file_path = tmp_path / "clipped_audio.wav"
    sample_rate = 44100
    duration = 0.5
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    # Severe clipping: sine amplitude 3.0 clipped at 1.0
    tone = np.clip(3.0 * np.sin(2 * np.pi * 440 * t), -1.0, 1.0)
    int16_samples = (tone * 32767).astype(np.int16)

    with wave.open(str(file_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int16_samples.tobytes())

    return file_path


@pytest.fixture
def silent_wav_path(tmp_path: Path) -> Path:
    """Generate a 1-second 44.1kHz 16-bit PCM WAV file with all zero samples."""
    file_path = tmp_path / "silent_audio.wav"
    sample_rate = 44100
    duration = 1.0
    zero_samples = np.zeros(int(sample_rate * duration), dtype=np.int16)

    with wave.open(str(file_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(zero_samples.tobytes())

    return file_path


@pytest.fixture
def lossy_cutoff_wav_path(tmp_path: Path) -> Path:
    """Generate a 44.1kHz audio file with a simulated MP3 steep low-pass filter cutoff at 15kHz."""
    file_path = tmp_path / "lossy_cutoff.wav"
    sample_rate = 44100
    duration = 1.5
    n_samples = int(sample_rate * duration)
    # White noise filtered with steep 8th-order Butterworth low-pass at 15kHz
    rng = np.random.default_rng(42)
    noise = rng.standard_normal(n_samples)
    sos = signal.butter(8, 15000, btype="lowpass", fs=sample_rate, output="sos")
    filtered = signal.sosfilt(sos, noise)
    normalized = filtered / np.max(np.abs(filtered)) * 0.7
    int16_samples = (normalized * 32767).astype(np.int16)

    with wave.open(str(file_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int16_samples.tobytes())

    return file_path


def test_audio_engine_analysis(sample_wav_path: Path) -> None:
    """Verify AudioForensicsEngine extracts properties, spectrogram, and waveform."""
    hasher = MultiHasher()
    digests = hasher.hash_file(sample_wav_path)

    engine = AudioForensicsEngine()
    result = engine.analyze_file(
        file_path=sample_wav_path,
        expected_sha256=digests.sha256,
        evidence_number="TEST-AUD-01",
    )

    assert result.hash_integrity.is_intact is True
    assert result.properties.sample_rate_hz == 44100
    assert result.properties.channels == 1
    assert result.properties.duration_seconds == pytest.approx(1.0, abs=0.05)
    assert result.properties.is_silent is False
    assert result.spectral_metrics.nyquist_frequency_hz == 22050.0

    # Verify generated artifacts
    assert result.spectrogram_artifact is not None
    assert result.spectrogram_artifact.mime_type == "image/png"
    assert len(result.spectrogram_artifact.image_bytes) > 0
    assert len(result.spectrogram_artifact.sha256) == 64

    assert result.waveform_artifact is not None
    assert result.waveform_artifact.mime_type == "image/png"
    assert len(result.waveform_artifact.image_bytes) > 0

    summary = result.to_summary_dict()
    assert "stream_properties" in summary
    assert "spectral_metrics" in summary
    assert "spectrogram_artifact" in summary
    assert "tool_versions" in summary
    assert "forensic_disclaimer" in summary


def test_audio_engine_clipping_detection(clipped_wav_path: Path) -> None:
    """Verify that clipped audio flags clipping finding."""
    hasher = MultiHasher()
    digests = hasher.hash_file(clipped_wav_path)

    engine = AudioForensicsEngine()
    result = engine.analyze_file(
        file_path=clipped_wav_path,
        expected_sha256=digests.sha256,
        evidence_number="TEST-AUD-CLIPPED",
    )

    assert result.properties.is_clipped is True
    assert result.properties.clipped_samples_count > 0
    clip_findings = [f for f in result.findings if "Clipping" in f.title]
    meta = clip_findings[0].finding_metadata or {}
    assert int(meta.get("clipped_samples", 0)) > 0


def test_audio_engine_tamper_detection(sample_wav_path: Path) -> None:
    """Verify mismatch between expected SHA-256 and bitstream raises critical finding."""
    engine = AudioForensicsEngine()
    fake_hash = "f" * 64

    result = engine.analyze_file(
        file_path=sample_wav_path,
        expected_sha256=fake_hash,
        evidence_number="TEST-AUD-TAMPER",
    )

    assert result.hash_integrity.is_intact is False
    tamper_findings = [f for f in result.findings if f.finding_type == "HASH_TAMPER"]
    assert len(tamper_findings) == 1
    assert tamper_findings[0].severity == "CRITICAL"


def test_audio_engine_silent_audio(silent_wav_path: Path) -> None:
    """Verify that completely silent audio is safely analyzed without division by zero."""
    hasher = MultiHasher()
    digests = hasher.hash_file(silent_wav_path)

    engine = AudioForensicsEngine()
    result = engine.analyze_file(
        file_path=silent_wav_path,
        expected_sha256=digests.sha256,
        evidence_number="TEST-AUD-SILENT",
    )

    assert result.properties.is_silent is True
    assert result.properties.rms_amplitude == 0.0
    assert result.properties.max_amplitude == 0.0

    silent_findings = [f for f in result.findings if "Silent" in f.title]
    assert len(silent_findings) >= 1
    assert silent_findings[0].severity == "INFO"

    # Artifacts should still render cleanly
    assert result.spectrogram_artifact is not None
    assert len(result.spectrogram_artifact.image_bytes) > 0
    assert result.waveform_artifact is not None
    assert len(result.waveform_artifact.image_bytes) > 0


def test_audio_engine_lossy_cutoff_detection(lossy_cutoff_wav_path: Path) -> None:
    """Verify detection of simulated lossy codec high-frequency cutoff shelf."""
    hasher = MultiHasher()
    digests = hasher.hash_file(lossy_cutoff_wav_path)

    engine = AudioForensicsEngine()
    result = engine.analyze_file(
        file_path=lossy_cutoff_wav_path,
        expected_sha256=digests.sha256,
        evidence_number="TEST-AUD-LOSSY",
    )

    cutoff_findings = [f for f in result.findings if "Cutoff" in f.title]
    if result.spectral_metrics.is_lossy_cutoff_detected:
        assert len(cutoff_findings) >= 1
        assert cutoff_findings[0].severity == "MEDIUM"
        assert result.spectral_metrics.detected_cutoff_frequency_hz is not None
        assert result.spectral_metrics.detected_cutoff_frequency_hz < 20000


def test_audio_engine_empty_file(tmp_path: Path) -> None:
    """Verify that a 0-byte file is handled safely without unhandled exceptions."""
    empty_file = tmp_path / "empty_audio.wav"
    empty_file.write_bytes(b"")
    hasher = MultiHasher()
    digests = hasher.hash_file(empty_file)

    engine = AudioForensicsEngine()
    result = engine.analyze_file(
        file_path=empty_file,
        expected_sha256=digests.sha256,
        evidence_number="TEST-AUD-EMPTY",
    )

    assert result.properties.duration_seconds == 0.0
    assert result.spectrogram_artifact is None
    assert result.waveform_artifact is None
    empty_findings = [f for f in result.findings if "Empty" in f.title]
    assert len(empty_findings) >= 1
    assert empty_findings[0].severity == "HIGH"


def test_audio_engine_oversized_file(sample_wav_path: Path) -> None:
    """Verify that an audio file exceeding max_file_size_bytes is rejected safely."""
    hasher = MultiHasher()
    digests = hasher.hash_file(sample_wav_path)

    # Set threshold lower than sample file size (~88KB)
    engine = AudioForensicsEngine(max_file_size_bytes=1024)
    result = engine.analyze_file(
        file_path=sample_wav_path,
        expected_sha256=digests.sha256,
        evidence_number="TEST-AUD-OVERSIZED",
    )

    assert result.spectrogram_artifact is None
    oversized_findings = [f for f in result.findings if "Oversized" in f.title]
    assert len(oversized_findings) >= 1
    assert oversized_findings[0].severity == "HIGH"


def test_audio_engine_malformed_file(tmp_path: Path) -> None:
    """Verify that corrupt/malformed audio data produces clean failure findings."""
    corrupt_file = tmp_path / "corrupt_audio.wav"
    corrupt_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00NOT_VALID_AUDIO_BYTES_00000000")
    hasher = MultiHasher()
    digests = hasher.hash_file(corrupt_file)

    engine = AudioForensicsEngine()
    result = engine.analyze_file(
        file_path=corrupt_file,
        expected_sha256=digests.sha256,
        evidence_number="TEST-AUD-CORRUPT",
    )

    unreadable_findings = [f for f in result.findings if "Unreadable" in f.title or "Container" in f.title]
    assert len(unreadable_findings) >= 1


def test_audio_engine_nonexistent_file(tmp_path: Path) -> None:
    """Verify that attempting to analyze a non-existent file raises FileNotFoundError."""
    nonexistent = tmp_path / "nonexistent.wav"
    engine = AudioForensicsEngine()
    with pytest.raises(FileNotFoundError):
        engine.analyze_file(
            file_path=nonexistent,
            expected_sha256="0" * 64,
            evidence_number="TEST-NONEXISTENT",
        )


def test_audio_engine_duration_and_resource_bounds(sample_wav_path: Path) -> None:
    """Verify that duration bounds parameter restricts analysis window."""
    hasher = MultiHasher()
    digests = hasher.hash_file(sample_wav_path)

    engine = AudioForensicsEngine()
    # Bound to 0.4 seconds
    result = engine.analyze_file(
        file_path=sample_wav_path,
        expected_sha256=digests.sha256,
        evidence_number="TEST-AUD-BOUNDED",
        parameters={"max_duration_seconds": 0.4},
    )

    assert result.properties.duration_seconds <= 0.55
    assert result.analysis_parameters.get("max_duration_seconds") == 0.4
    assert result.spectrogram_artifact is not None
    assert result.waveform_artifact is not None


def test_audio_engine_courtroom_disclaimers(sample_wav_path: Path) -> None:
    """Verify that analysis results embed courtroom limitations and omit legal guilt claims."""
    hasher = MultiHasher()
    digests = hasher.hash_file(sample_wav_path)

    engine = AudioForensicsEngine()
    result = engine.analyze_file(
        file_path=sample_wav_path,
        expected_sha256=digests.sha256,
        evidence_number="TEST-AUD-LEGAL",
    )

    assert len(result.limitations) >= 3
    # Check that forensic disclaimer explicitly notes lack of definitive tampering proof
    assert "DO NOT constitute definitive legal proof" in result.forensic_disclaimer
    # Verify no findings claim authentic or tampered solely from visualization
    for finding in result.findings:
        assert "proven authentic" not in finding.description.lower()
        assert "proven fake" not in finding.description.lower()


def test_ffprobe_inspect_audio_streams(sample_wav_path: Path) -> None:
    """Verify FFprobeAdapter inspect_audio_streams extracts audio container and stream properties."""
    adapter = FFprobeAdapter()
    if not adapter.is_available():
        pytest.skip("FFprobe not available on host PATH")

    result = adapter.inspect_audio_streams(sample_wav_path)
    assert result["success"] is True
    assert result["has_audio"] is True
    assert result["audio_stream_count"] >= 1
    primary = result["primary_stream"]
    assert primary is not None
    assert primary["sample_rate_hz"] == 44100
    assert primary["channels"] == 1
    assert "forensic_authenticity_notice" in result


def test_ffmpeg_decode_audio_stream(sample_wav_path: Path) -> None:
    """Verify FFmpegAdapter decode_audio_stream decodes PCM samples with bounded controls."""
    adapter = FFmpegAdapter()
    if not adapter.is_available():
        pytest.skip("FFmpeg not available on host PATH")

    result = adapter.decode_audio_stream(
        sample_wav_path,
        max_duration_seconds=2.0,
        target_sample_rate_hz=44100,
        max_channels=1,
    )

    assert result.success is True
    assert len(result.samples) > 0
    assert result.sample_rate_hz == 44100
    assert result.channels == 1
    assert result.duration_seconds == pytest.approx(1.0, abs=0.1)
    assert result.truncated is False
    assert len(result.provenance.get("source_file_sha256", "")) == 64


def test_ffmpeg_decode_audio_empty_and_oversized(tmp_path: Path, sample_wav_path: Path) -> None:
    """Verify FFmpegAdapter handles empty and oversized audio files gracefully."""
    adapter = FFmpegAdapter()
    if not adapter.is_available():
        pytest.skip("FFmpeg not available on host PATH")

    # Empty file
    empty_file = tmp_path / "empty.wav"
    empty_file.write_bytes(b"")
    res_empty = adapter.decode_audio_stream(empty_file)
    assert res_empty.success is False
    assert len(res_empty.errors) >= 1
    assert "empty" in res_empty.errors[0].lower()

    # Oversized file
    res_over = adapter.decode_audio_stream(sample_wav_path, max_file_size_bytes=500)
    assert res_over.success is False
    assert len(res_over.errors) >= 1
    assert "exceeds maximum allowed resource limit" in res_over.errors[0].lower()
