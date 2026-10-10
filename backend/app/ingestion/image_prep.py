"""Validation and conservative preprocessing for OCR image uploads.

Validation trusts the file's actual content (decoded by Pillow), never the
extension or the client-declared content type, and enforces a pixel cap
before the image is decoded so a tiny, highly-compressed file cannot declare
billions of pixels and exhaust memory.

Preprocessing is deliberately conservative: EXIF orientation, a size clamp,
grayscale, and a mild contrast stretch. It does NOT binarise, denoise, sharpen
or deskew — those transforms erase decimal points, units, thin reference-range
dashes and faint handwriting, which is exactly the clinical text we must keep.
"""
import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

# PIL format name -> (canonical extension, media type)
ALLOWED_FORMATS: dict[str, tuple[str, str]] = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MEDIA_TYPE_BY_EXTENSION = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

# Images smaller than this on their longest side are upscaled for OCR only.
# Measured on a rendered lab report (see tests/test_image_upload.py): at native
# 1100px the recogniser dropped word spaces ("Patient Name:MeeraKrishnan",
# "Vitamin D18") and mangled "30 - 100"; from ~2x up the same text came back
# exactly. Boxes are mapped back to original coordinates afterwards.
_MIN_OCR_LONG_SIDE = 2000
_MAX_UPSCALE = 3.0


class ImageValidationError(Exception):
    """The upload is not an acceptable image. The message is user-safe.
    `unsupported` distinguishes a wrong file type (HTTP 400, like the PDF
    uploader) from a supported type that is empty/corrupt/too large (422)."""

    def __init__(self, message: str, unsupported: bool = False):
        super().__init__(message)
        self.unsupported = unsupported


@dataclass
class ValidatedImage:
    format: str
    extension: str
    media_type: str
    width: int
    height: int


@dataclass
class PreparedImage:
    array: np.ndarray  # what the OCR engine reads (grayscale, uint8)
    scale: float  # processed_px / original_px — divide engine coordinates by this
    width: int  # original size in display orientation (EXIF applied)
    height: int


def validate_image(data: bytes, file_name: str, max_pixels: int) -> ValidatedImage:
    if not data:
        raise ImageValidationError(f"'{file_name}' is empty.")

    lowered = file_name.lower()
    if not any(lowered.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise ImageValidationError("Only JPG, PNG, and WEBP images are supported.", unsupported=True)

    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format
            width, height = img.size
            # Checked from the header, before any pixel data is decoded.
            if width * height > max_pixels:
                raise ImageValidationError(
                    f"This image is too large to process safely ({width}x{height}). "
                    f"The limit is {max_pixels // 1_000_000} megapixels."
                )
            if fmt not in ALLOWED_FORMATS:
                raise ImageValidationError("Only JPG, PNG, and WEBP images are supported.", unsupported=True)
            img.verify()
    except ImageValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise ImageValidationError(f"'{file_name}' is not a readable image.") from exc

    extension, media_type = ALLOWED_FORMATS[fmt]
    # Orientation can swap the displayed width/height; report display size.
    try:
        with Image.open(io.BytesIO(data)) as img:
            display = ImageOps.exif_transpose(img)
            width, height = display.size
    except (OSError, SyntaxError, ValueError) as exc:
        raise ImageValidationError(f"'{file_name}' is not a readable image.") from exc

    return ValidatedImage(format=fmt, extension=extension, media_type=media_type, width=width, height=height)


def prepare_for_ocr(data: bytes, max_side: int) -> PreparedImage:
    with Image.open(io.BytesIO(data)) as raw:
        img = ImageOps.exif_transpose(raw).convert("RGB")
    width, height = img.size

    longest = max(width, height)
    scale = 1.0
    if longest > max_side:
        scale = max_side / longest
    elif longest < _MIN_OCR_LONG_SIDE:
        scale = min(_MAX_UPSCALE, _MIN_OCR_LONG_SIDE / longest)
    if scale != 1.0:
        img = img.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS)

    gray = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=1)
    return PreparedImage(array=np.array(gray), scale=scale, width=width, height=height)
