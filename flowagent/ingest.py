"""Read a source PDF: its bytes for the model, and its text for the checker.

The text is what grounding checks quotes against, so where it came from matters:
  text_layer  embedded in the PDF (best)
  ocr         tesseract on a rendered page (independent of the model, noisier)
  ""          neither tool is installed: grounding against the source is skipped
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

MIN_WORDS = 20  # fewer than this and the page is treated as an image


@dataclass
class Source:
    path: Path
    pdf_bytes: bytes
    text: str
    kind: str
    pages: int = 1


def _run(args: list[str]) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=180, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def read_source(path: str | Path, ocr: bool = True) -> Source:
    path = Path(path)
    data = path.read_bytes()
    text, kind = "", ""
    if path.suffix.lower() == ".txt":
        return Source(path, b"", data.decode("utf-8"), "text_layer")
    if shutil.which("pdftotext"):
        text = _run(["pdftotext", "-layout", str(path), "-"])
        kind = "text_layer"
    if len(text.split()) < MIN_WORDS:
        text, kind = "", ""
        if ocr and shutil.which("pdftoppm") and shutil.which("tesseract"):
            text = _ocr(path)
            kind = "ocr" if text.strip() else ""
    pages = max(1, text.count("\f")) if text else 1
    return Source(path, data, text, kind, pages)


def _ocr(path: Path) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        _run(["pdftoppm", "-r", "300", "-png", str(path), f"{tmp}/p"])
        pages = sorted(Path(tmp).glob("p*.png"))
        # psm 12: sparse text with orientation detection; scanned charts are often rotated
        return "\f".join(_run(["tesseract", str(p), "-", "--psm", "12"]) for p in pages)
