"""Cryptographic and forensic file signature (magic byte) validator.

Ensures uploaded files conform to accepted digital media categories:
- IMAGE (JPEG, PNG, GIF, WebP, TIFF, BMP)
- AUDIO (MP3, WAV, FLAC, OGG, AAC, M4A)
- VIDEO (MP4, MKV/WebM, AVI, QuickTime MOV, MPEG)

Rejects empty files, executables, documents, archives, and mismatched file types
regardless of client-provided Content-Type or file extensions.
"""

from __future__ import annotations

import logging
from typing import Final

from fastapi import HTTPException, status

from app.db.models.evidence import MediaType

logger = logging.getLogger("ps05.file_validator")

# Header read length required to inspect major brands and magic bytes
HEADER_READ_LENGTH: Final[int] = 8192

# Known dangerous / non-media magic signatures for explicit diagnostics
_DISALLOWED_SIGNATURES: Final[dict[bytes, str]] = {
    b"MZ": "Windows Executable / DLL (PE)",
    b"\x7fELF": "Linux Executable (ELF)",
    b"%PDF-": "PDF Document",
    b"PK\x03\x04": "ZIP / Office Archive",
    b"\xca\xfe\xba\xbe": "Java Class / Mach-O Binary",
    b"\xfeedface": "Mach-O 32-bit",
    b"\xfeedfacf": "Mach-O 64-bit",
    b"\xcf\xfa\xed\xfe": "Mach-O Reverse 64-bit",
    b"7z\xbc\xaf\x27\x1c": "7-Zip Archive",
    b"Rar!\x1a\x07": "RAR Archive",
    b"\x1f\x8b": "Gzip Compressed File",
    b"BZh": "Bzip2 Compressed File",
    b"#!": "Shell Script",
    b"<!DOCTYPE html": "HTML Document",
    b"<html": "HTML Document",
    b"<?xml": "XML Document",
}


def detect_media_signature(header: bytes) -> tuple[MediaType, str]:
    """
    Inspect raw initial bytes to determine verified MediaType and MIME string.

    Raises HTTPException:
    - 400 with code 'EMPTY_FILE' if header length is 0.
    - 400 with code 'UNSUPPORTED_MEDIA_TYPE' if header matches a non-media signature.
    - 400 with code 'INVALID_FILE_SIGNATURE' if no valid image/audio/video signature matches.
    """
    if not header or len(header) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "EMPTY_FILE",
                "message": "Uploaded evidence file is empty (0 bytes). Intake rejected.",
            },
        )

    # 1. Check for explicitly forbidden non-media signatures
    for sig, desc in _DISALLOWED_SIGNATURES.items():
        if header.startswith(sig):
            logger.warning("Rejected non-media payload with signature '%s': %s", sig, desc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "UNSUPPORTED_MEDIA_TYPE",
                    "message": f"Rejected disallowed file format '{desc}'. Evidence intake only accepts image, audio, and video files.",
                },
            )

    # 2. IMAGE SIGNATURES
    # JPEG: FF D8 FF
    if header.startswith(b"\xff\xd8\xff"):
        return MediaType.IMAGE, "image/jpeg"

    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return MediaType.IMAGE, "image/png"

    # GIF: GIF87a or GIF89a
    if header.startswith((b"GIF87a", b"GIF89a")):
        return MediaType.IMAGE, "image/gif"

    # WebP: RIFF .... WEBP
    if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return MediaType.IMAGE, "image/webp"

    # TIFF: II*\x00 (little-endian) or MM\x00* (big-endian)
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return MediaType.IMAGE, "image/tiff"

    # BMP: BM
    if header.startswith(b"BM") and len(header) >= 14:
        return MediaType.IMAGE, "image/bmp"

    # 3. AUDIO SIGNATURES
    # FLAC: fLaC
    if header.startswith(b"fLaC"):
        return MediaType.AUDIO, "audio/flac"

    # OGG: OggS
    if header.startswith(b"OggS"):
        return MediaType.AUDIO, "audio/ogg"

    # WAV: RIFF .... WAVE
    if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return MediaType.AUDIO, "audio/wav"

    # MP3 with ID3v2 tag
    if header.startswith(b"ID3"):
        return MediaType.AUDIO, "audio/mpeg"

    # Raw MP3 frame sync: 11 bits set (0xFF followed by 0xE0 mask)
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        # Check layer bits (bits 1,2 of header[1] must not be 00)
        layer = (header[1] >> 1) & 0x03
        if layer != 0:
            return MediaType.AUDIO, "audio/mpeg"

    # AAC (ADTS): FF F1 or FF F9
    if header.startswith((b"\xff\xf1", b"\xff\xf9")):
        return MediaType.AUDIO, "audio/aac"

    # 4. VIDEO & ISO BASE MEDIA FILE FORMAT (MP4, MOV, M4A)
    # Check for Box structure: offset 4 is 'ftyp'
    if len(header) >= 12 and header[4:8] == b"ftyp":
        major_brand = header[8:12]

        # Audio-specific ISO brands
        if major_brand in (b"M4A ", b"M4B "):
            return MediaType.AUDIO, "audio/mp4"

        # QuickTime MOV
        if major_brand == b"qt  ":
            return MediaType.VIDEO, "video/quicktime"

        # Standard MP4 video brands
        if major_brand in (
            b"isom",
            b"iso2",
            b"mp41",
            b"mp42",
            b"MSNV",
            b"avc1",
            b"dash",
            b"XAVC",
            b"NDSC",
        ):
            return MediaType.VIDEO, "video/mp4"

        # Any other ftyp is generally an ISO MP4 container
        return MediaType.VIDEO, "video/mp4"

    # QuickTime MOV atom headers without ftyp
    if len(header) >= 8 and header[4:8] in (b"moov", b"mdat", b"wide", b"free", b"skip"):
        return MediaType.VIDEO, "video/quicktime"

    # Matroska / WebM: EBML header 1A 45 DF A3
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        # Check for webm docType string inside first 64 bytes
        if b"webm" in header[:64]:
            return MediaType.VIDEO, "video/webm"
        return MediaType.VIDEO, "video/x-matroska"

    # AVI: RIFF .... AVI
    if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"AVI ":
        return MediaType.VIDEO, "video/x-msvideo"

    # MPEG Video Stream: 00 00 01 BA (MPEG-PS) or 00 00 01 B3 (MPEG Video)
    if header.startswith((b"\x00\x00\x01\xba", b"\x00\x00\x01\xb3")):
        return MediaType.VIDEO, "video/mpeg"

    logger.warning("Unrecognized file signature for header hex: %s", header[:16].hex())
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "INVALID_FILE_SIGNATURE",
            "message": "File signature (magic bytes) does not match any accepted image, audio, or video media format.",
        },
    )
