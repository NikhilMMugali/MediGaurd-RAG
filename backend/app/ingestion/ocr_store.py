"""Persists an image's OCR result next to the stored original, as
`<document_id>.ocr.json` in the upload directory.

Keeps the exact lines, confidences and boxes the engine produced so that
(a) the source viewer can highlight real regions instead of guessing,
(b) a retry after a partial failure resumes from the stored text rather than
re-running OCR, and (c) the extracted-text preview is available even for an
image that was sent to review and never indexed.
"""
import json
import os
from pathlib import Path

from app.config import get_settings
from app.ingestion.ocr_engine import OcrLine, OcrResult

_SCHEMA_VERSION = 1


def _path(document_id: str) -> Path:
    return Path(get_settings().upload_dir) / f"{document_id}.ocr.json"


def save_ocr(document_id: str, result: OcrResult, quality: str, problem: str | None) -> None:
    path = _path(document_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _SCHEMA_VERSION,
        "engine": result.engine,
        "width": result.width,
        "height": result.height,
        "mean_confidence": round(result.mean_confidence, 4),
        "quality": quality,
        "problem": problem,
        "lines": [{"text": ln.text, "confidence": round(ln.confidence, 4), "box": [round(v, 1) for v in ln.box]} for ln in result.lines],
    }
    # Write-then-rename so a crash mid-write never leaves a truncated file
    # that a later retry would mistake for a finished OCR result.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)


def load_ocr(document_id: str) -> dict | None:
    path = _path(document_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("version") != _SCHEMA_VERSION or not isinstance(data.get("lines"), list):
        return None
    return data


def result_from_stored(data: dict) -> OcrResult:
    return OcrResult(
        lines=[OcrLine(text=ln["text"], confidence=float(ln["confidence"]), box=[float(v) for v in ln["box"]]) for ln in data["lines"]],
        width=int(data["width"]),
        height=int(data["height"]),
        engine=data.get("engine", "rapidocr-onnxruntime"),
    )
