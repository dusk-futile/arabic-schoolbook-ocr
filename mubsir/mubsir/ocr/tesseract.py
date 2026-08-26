"""Tesseract 5 front-end.

Benchmarked against the alternatives on the same gold set, this is the best
Arabic recogniser that fits the hardware budget: same character error as
PP-OCRv4 but a little over a third of its word error, at half the time. Word
error is what a proofreader actually pays for - a word is either right or it
has to be retyped.

Tesseract is a binary rather than a wheel, so it is optional: the engine
reports itself unavailable and the pipeline falls back to the pure-pip
recogniser. `tessdata_best` is preferred over the standard models (CER 0.070
vs 0.103) and is bundled.
"""
from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..model import Line
from .engine import MODELS_DIR, OCREngine

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Searched in order. The bundled micromamba environment first, so a machine
# without an admin-installed Tesseract still works.
BINARY_CANDIDATES = [
    os.path.join(_ROOT, ".mm-tess", "bin", "tesseract"),
    os.path.join(_ROOT, ".mm-tess", "Library", "bin", "tesseract.exe"),
    os.path.join(_ROOT, "tesseract", "tesseract.exe"),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

TESSDATA_CANDIDATES = [
    os.path.join(MODELS_DIR, "tessdata_best"),
    os.path.join(_ROOT, ".mm-tess", "share", "tessdata"),
    os.path.join(_ROOT, ".mm-tess", "Library", "share", "tessdata"),
]


def find_binary() -> Optional[str]:
    for p in BINARY_CANDIDATES:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return shutil.which("tesseract")


def find_tessdata(langs: str = "ara") -> Optional[str]:
    need = [f"{l}.traineddata" for l in langs.split("+")]
    for p in TESSDATA_CANDIDATES:
        if os.path.isdir(p) and all(os.path.exists(os.path.join(p, n)) for n in need):
            return p
    env = os.environ.get("TESSDATA_PREFIX")
    if env and os.path.isdir(env):
        return env
    return None


def available(langs: str = "ara") -> bool:
    return bool(find_binary()) and bool(find_tessdata(langs))


class TesseractEngine(OCREngine):
    name = "tesseract"

    def __init__(self, langs: str = "ara", psm: int = 6, binary: Optional[str] = None,
                 tessdata: Optional[str] = None, timeout: int = 300):
        self.binary = binary or find_binary()
        self.tessdata = tessdata or find_tessdata(langs)
        if not self.binary or not self.tessdata:
            raise RuntimeError(
                "Tesseract not found. Install it, or run setup which fetches a "
                "user-local copy needing no administrator rights."
            )
        self.langs = langs
        self.psm = psm
        self.timeout = timeout

    def _run_tsv(self, img_path: str) -> str:
        env = dict(os.environ, TESSDATA_PREFIX=os.path.abspath(self.tessdata))
        proc = subprocess.run(
            [self.binary, img_path, "stdout", "-l", self.langs,
             "--psm", str(self.psm), "tsv"],
            capture_output=True, env=env, timeout=self.timeout,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", "replace")[:400])
        return proc.stdout.decode("utf-8", "replace")

    def page_lines(self, img_bgr, page_no: int, scale: float) -> List[Line]:
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "page.png")
            cv2.imwrite(path, img_bgr)
            tsv = self._run_tsv(path)

        # Words are emitted individually and grouped into lines downstream by
        # the shared baseline merger, NOT by Tesseract's own block/par/line
        # numbering. Tesseract's grouping drops short paragraph-final lines
        # (it folded "والحيوانات المخبرية." into its neighbour), and a short
        # final line is precisely the signal paragraph detection rests on.
        words: List[dict] = []
        reader = csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
        for row in reader:
            try:
                if int(row["level"]) != 5:
                    continue
                conf = float(row["conf"])
            except (TypeError, ValueError, KeyError):
                continue
            text = (row.get("text") or "").strip()
            if not text or conf < 0:
                continue
            words.append({
                "text": text, "conf": conf / 100.0,
                "left": int(row["left"]), "top": int(row["top"]),
                "width": int(row["width"]), "height": int(row["height"]),
            })

        if not words:
            return []

        # A word box hugs its own ink, so its height depends on whether that
        # word happens to have an ascender or a descender. The page's median
        # word height is a far steadier estimate of body type size, and the
        # structure engine keys several decisions off size.
        heights = sorted(w["height"] for w in words)
        median_h = heights[len(heights) // 2] or 1

        out: List[Line] = []
        for w in words:
            x0, y0 = w["left"], w["top"]
            x1, y1 = w["left"] + w["width"], w["top"] + w["height"]
            h = w["height"]
            size = (h if h > median_h * 1.35 else median_h) / scale * 0.78
            out.append(Line(
                text=w["text"],
                bbox=(x0 / scale, y0 / scale, x1 / scale, y1 / scale),
                page=page_no,
                size=round(size, 2),
                conf=w["conf"],
                source="ocr",
            ))
        out.sort(key=lambda l: (l.y0, -l.x1))
        return out
