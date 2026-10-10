"""Local OCR (RapidOCR: PaddleOCR detection/recognition models on ONNX Runtime).

Chosen over Tesseract because it installs with pip alone — the models ship
inside the wheel, there is no system binary to be missing — runs fully on the
local machine (patient documents never leave it), and reports a confidence and
a bounding box per text line, which the source viewer uses for highlighting.

The engine is created lazily and once (loading the models takes a couple of
seconds). A missing/broken install raises OcrUnavailableError instead of
failing silently, so an upload is marked failed with a clear reason rather
than reported as a success with no text.
"""
import statistics
import threading
from dataclasses import dataclass, field

from app.ingestion.image_prep import PreparedImage

_engine = None
_engine_lock = threading.Lock()


class OcrUnavailableError(Exception):
    """The OCR engine is not installed or could not be initialised."""


@dataclass
class OcrLine:
    text: str
    confidence: float  # 0..1
    # Axis-aligned box [x1, y1, x2, y2] in the ORIGINAL image's pixel space
    # (display orientation), mapped back from the preprocessed image.
    box: list[float]


@dataclass
class OcrResult:
    lines: list[OcrLine]
    width: int
    height: int
    engine: str = "rapidocr-onnxruntime"
    notes: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def mean_confidence(self) -> float:
        if not self.lines:
            return 0.0
        # Weighted by text length so a few long, confident lines are not
        # dragged down by many one-character noise detections.
        total = sum(len(line.text) for line in self.lines) or 1
        return sum(line.confidence * len(line.text) for line in self.lines) / total


def _get_engine():
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR

                _engine = RapidOCR()
            except Exception as exc:  # noqa: BLE001 — any import/model-load failure
                raise OcrUnavailableError(
                    "The OCR engine is not available on this server (rapidocr-onnxruntime failed to load)."
                ) from exc
    return _engine


def _reading_order(raw: list[tuple[list[list[float]], str, float]]) -> list[tuple[list[list[float]], str, float]]:
    """Top-to-bottom, then left-to-right within a row, so table cells come out
    as 'label value unit range' rather than column by column."""
    if not raw:
        return raw
    heights = [max(p[1] for p in box) - min(p[1] for p in box) for box, _, _ in raw]
    row_tolerance = 0.6 * (statistics.median(heights) or 1.0)

    def center_y(item):
        return sum(p[1] for p in item[0]) / 4

    rows: list[list] = []
    for item in sorted(raw, key=center_y):
        if rows and abs(center_y(item) - statistics.mean(center_y(i) for i in rows[-1])) <= row_tolerance:
            rows[-1].append(item)
        else:
            rows.append([item])
    ordered = []
    for row in rows:
        ordered.extend(sorted(row, key=lambda it: min(p[0] for p in it[0])))
    return ordered


def run_ocr(prepared: PreparedImage) -> OcrResult:
    engine = _get_engine()
    try:
        with _engine_lock:  # one image at a time; the engine object is not documented as thread-safe
            result, _elapsed = engine(prepared.array)
    except Exception as exc:  # noqa: BLE001
        raise OcrUnavailableError("The OCR engine failed while reading this image.") from exc

    raw = []
    for item in result or []:
        box, text, score = item[0], str(item[1]).strip(), float(item[2])
        if text:
            raw.append((box, text, score))

    lines = []
    for box, text, score in _reading_order(raw):
        xs = [p[0] / prepared.scale for p in box]
        ys = [p[1] / prepared.scale for p in box]
        lines.append(
            OcrLine(
                text=text,
                confidence=max(0.0, min(1.0, score)),
                box=[
                    max(0.0, min(xs)),
                    max(0.0, min(ys)),
                    min(float(prepared.width), max(xs)),
                    min(float(prepared.height), max(ys)),
                ],
            )
        )
    return OcrResult(lines=lines, width=prepared.width, height=prepared.height)


def assess_quality(result: OcrResult, min_confidence: float, min_chars: int) -> tuple[str, str | None]:
    """Returns (label, problem). label: 'good' | 'fair' | 'poor'. A non-None
    problem means the result must be reviewed by a person, not indexed."""
    chars = len(result.text.replace("\n", "").replace(" ", ""))
    if chars < min_chars:
        return "poor", "Very little text could be read from this image — it may be blank, blurred, or not a document."
    mean = result.mean_confidence
    if mean < min_confidence:
        return "poor", f"The text could only be read with low confidence ({mean:.0%}). Please retake the photo or upload a clearer image."
    return ("good" if mean >= 0.85 else "fair"), None
