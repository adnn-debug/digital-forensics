"""
Cryptographic verification seals, QR codes, and evidentiary markers for courtroom reports.
"""

from __future__ import annotations

import io

import qrcode
from qrcode.image.pil import PilImage


def generate_qr_seal_bytes(
    verification_payload: str,
    box_size: int = 4,
    border: int = 2,
) -> bytes:
    """
    Generate high-density verification QR code PNG bytes.

    Encodes case verification URL and document cryptographic SHA-256 hash
    for courtroom scan-to-verify authentication.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(verification_payload)
    qr.make(fit=True)

    img: PilImage = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
