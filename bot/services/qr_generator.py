"""QR code generation for VLESS links."""

from __future__ import annotations

import io
from typing import Optional

from loguru import logger

try:
    import qrcode

    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False


def generate_qr_bytes(data: str) -> Optional[bytes]:
    if not HAS_QRCODE:
        logger.warning("qrcode library not installed, cannot generate QR")
        return None

    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.error("QR generation failed: {}", e)
        return None


def generate_qr_buffer(data: str) -> Optional[io.BytesIO]:
    raw = generate_qr_bytes(data)
    if raw is None:
        return None
    buf = io.BytesIO(raw)
    buf.name = "vpn_key_qr.png"
    return buf
