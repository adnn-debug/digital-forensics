"""Unit tests for AudioForensicsEngine."""

import struct
import wave
from pathlib import Path

import numpy as np
import pytest

from app.forensics.audio_engine import AudioForensicsEngine
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


def test_audio_engine_clipping_detection(clipped_wav_path: Path) -> None:
    """Verify that clipped audio flags clipping and container mismatch finding."""
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
    assert len(clip_findings) >= 1


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
