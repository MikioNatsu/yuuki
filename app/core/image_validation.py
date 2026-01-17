from __future__ import annotations

import hashlib
from io import BytesIO

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError

from app.core.errors import (
    ImageDimensionsExceededError,
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedImageTypeError,
)
from app.domain.entities import ValidatedImage


_FORMAT_TO_MIME: dict[str, str] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


async def read_upload_limited(*, upload: UploadFile, max_bytes: int, chunk_size: int) -> tuple[bytes, str]:
    if max_bytes <= 0:
        raise ImageTooLargeError("invalid max_bytes configuration")
    if chunk_size <= 0:
        chunk_size = 64 * 1024

    digest = hashlib.sha256()
    buf = bytearray()

    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        digest.update(chunk)
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise ImageTooLargeError("upload exceeded configured max size")

    data = bytes(buf)
    if not data:
        raise InvalidImageError("empty upload")

    return data, digest.hexdigest()


def parse_and_validate_image_bytes(
    *,
    data: bytes,
    sha256_hex: str,
    allowed_mime_types: list[str],
    max_pixels: int,
    max_width: int,
    max_height: int,
) -> ValidatedImage:
    try:
        with Image.open(BytesIO(data)) as img:
            img.verify()
    except DecompressionBombError as exc:
        raise ImageDimensionsExceededError("decompression bomb detected") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImageError("failed image verify") from exc

    try:
        with Image.open(BytesIO(data)) as img2:
            img2.load()
            width, height = img2.size
            fmt = (img2.format or "").upper()
    except DecompressionBombError as exc:
        raise ImageDimensionsExceededError("decompression bomb detected") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImageError("failed image load") from exc

    if width <= 0 or height <= 0:
        raise InvalidImageError("invalid image dimensions")

    pixels = width * height
    if pixels > max_pixels or width > max_width or height > max_height:
        raise ImageDimensionsExceededError("image dimensions exceeded limits")

    mime = _FORMAT_TO_MIME.get(fmt, "")
    if not mime:
        raise UnsupportedImageTypeError(f"unsupported image format: {fmt!r}")

    allowed = {m.strip().lower() for m in allowed_mime_types if m.strip()}
    if mime.lower() not in allowed:
        raise UnsupportedImageTypeError(f"mime type not allowed: {mime!r}")

    return ValidatedImage(
        content=data,
        mime_type=mime,
        sha256=sha256_hex,
        width=width,
        height=height,
    )
