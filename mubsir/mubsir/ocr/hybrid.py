"""Detector from one engine, recogniser from the other.

Measured separately on the same gold set, the two engines fail in opposite
directions:

  * DBNet (PP-OCR's detector) finds every line, including the short
    paragraph-final ones that carry the paragraph-break signal.
  * Tesseract reads Arabic far more accurately - roughly a third of PP-OCR's
    word error - but its layout analysis silently drops those same short
    isolated lines. Every page-segmentation mode drops them, so it is not a
    tuning problem.

Losing a paragraph-final line is expensive twice over: the text is gone, and
the strongest structural cue goes with it. So detection comes from DBNet and
recognition from Tesseract.

Recognition is batched by stacking every line crop into one tall canvas with
wide white gutters and running Tesseract once. Calling it per crop would be
cleaner but costs a process launch and a 12 MB model load per line - about
10 s a page against 2 s. Because the canvas layout is constructed here, each
output word maps back to its source line by vertical position rather than by
trusting Tesseract's own line numbering.
"""
from __future__ import annotations

import csv
import io
import os
import subprocess
import tempfile
from typing import List, Optional, Tuple

import cv2
import numpy as np

from ..model import Line
from .engine import OCREngine
from .tesseract import find_binary, find_tessdata

# Separation between stacked crops, as a fraction of each crop's own height.
# A fixed pixel pad is wrong: 26 px is generous at 100 dpi and negligible at
# 300, where Tesseract merges neighbouring crops into one line and their words
# get attributed to the wrong source line - or dropped.
PAD_RATIO = 0.75
PAD_MIN = 24
PAD_X = 24
MAX_CANVAS_H = 60000


class HybridEngine(OCREngine):
    name = "hybrid-dbnet-tesseract"

    def __init__(self, langs: str = "ara", timeout: int = 600):
        from rapidocr_onnxruntime import RapidOCR
        self.binary = find_binary()
        self.tessdata = find_tessdata(langs)
        if not self.binary or not self.tessdata:
            raise RuntimeError("Tesseract not available for the hybrid engine")
        self.langs = langs
        self.timeout = timeout
        self._det = RapidOCR()

    # ------------------------------------------------------------ detection
    def detect(self, img_bgr) -> List[Tuple[int, int, int, int]]:
        res, _ = self._det(img_bgr, use_det=True, use_cls=False, use_rec=False)
        if not res:
            return []
        H, W = img_bgr.shape[:2]
        boxes = []
        for b in res:
            arr = np.array(b, dtype=np.float32)
            x0 = int(max(0, arr[:, 0].min()))
            y0 = int(max(0, arr[:, 1].min()))
            x1 = int(min(W, arr[:, 0].max()))
            y1 = int(min(H, arr[:, 1].max()))
            if x1 - x0 >= 8 and y1 - y0 >= 8:
                boxes.append((x0, y0, x1, y1))
        boxes.sort(key=lambda b: (b[1], -b[2]))
        return boxes

    # ---------------------------------------------------------- recognition
    @staticmethod
    def _pad_for(h: int) -> int:
        return max(PAD_MIN, int(h * PAD_RATIO))

    def _stack(self, crops: List[np.ndarray]) -> Tuple[np.ndarray, List[Tuple[int, int]]]:
        cw = max(c.shape[1] for c in crops) + 2 * PAD_X
        ch = sum(c.shape[0] + 2 * self._pad_for(c.shape[0]) for c in crops)
        canvas = np.full((min(ch, MAX_CANVAS_H), cw, 3), 255, np.uint8)
        spans: List[Tuple[int, int]] = []
        y = 0
        for crop in crops:
            h, w = crop.shape[:2]
            pad = self._pad_for(h)
            top = y + pad
            if top + h >= canvas.shape[0]:
                spans.append((-1, -1))
                continue
            canvas[top:top + h, PAD_X:PAD_X + w] = crop
            spans.append((top, top + h))
            y = top + h + pad
        return canvas, spans

    def _recognise_one(self, crop: np.ndarray) -> List[dict]:
        """Fallback for a crop the stacked pass lost: recognise it alone.

        Costs a process launch, so it only runs for crops that came back empty
        - a handful a page at worst, and never on a clean page."""
        pad = self._pad_for(crop.shape[0])
        canvas = np.full((crop.shape[0] + 2 * pad, crop.shape[1] + 2 * PAD_X, 3),
                         255, np.uint8)
        canvas[pad:pad + crop.shape[0], PAD_X:PAD_X + crop.shape[1]] = crop
        try:
            return self._tsv(canvas, psm=7)
        except Exception:
            return []

    def _tsv(self, img: np.ndarray, psm: int = 6) -> List[dict]:
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "stack.png")
            cv2.imwrite(path, img)
            env = dict(os.environ, TESSDATA_PREFIX=os.path.abspath(self.tessdata))
            proc = subprocess.run(
                [self.binary, path, "stdout", "-l", self.langs, "--psm", str(psm), "tsv"],
                capture_output=True, env=env, timeout=self.timeout,
            )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", "replace")[:300])
        out = []
        reader = csv.DictReader(io.StringIO(proc.stdout.decode("utf-8", "replace")),
                                delimiter="\t", quoting=csv.QUOTE_NONE)
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
            out.append({"text": text, "conf": conf / 100.0,
                        "left": int(row["left"]), "top": int(row["top"]),
                        "height": int(row["height"]), "width": int(row["width"])})
        return out

    def page_lines(self, img_bgr, page_no: int, scale: float) -> List[Line]:
        boxes = self.detect(img_bgr)
        if not boxes:
            return []
        H, W = img_bgr.shape[:2]
        crops = []
        for (x0, y0, x1, y1) in boxes:
            pad = max(2, int((y1 - y0) * 0.12))
            crops.append(img_bgr[max(0, y0 - pad):min(H, y1 + pad), x0:x1])
        canvas, spans = self._stack(crops)
        words = self._tsv(canvas)

        # Assign each recognised word to the crop whose band contains its centre.
        buckets: List[List[dict]] = [[] for _ in boxes]
        for w in words:
            cy = w["top"] + w["height"] / 2
            for i, (top, bot) in enumerate(spans):
                if top < 0:
                    continue
                slack = self._pad_for(bot - top) * 0.45
                if top - slack <= cy <= bot + slack:
                    buckets[i].append(w)
                    break

        lines: List[Line] = []
        self.retries = 0
        for i, (x0, y0, x1, y1) in enumerate(boxes):
            got = buckets[i]
            if not got:
                got = self._recognise_one(crops[i])
                self.retries += 1
            if not got:
                continue
            got.sort(key=lambda w: -(w["left"] + w["width"]))   # RTL
            text = " ".join(w["text"] for w in got)
            if not text.strip():
                continue
            lines.append(Line(
                text=text,
                bbox=(x0 / scale, y0 / scale, x1 / scale, y1 / scale),
                page=page_no,
                size=(y1 - y0) / scale * 0.78,
                conf=float(np.mean([w["conf"] for w in got])),
                source="ocr",
            ))
        lines.sort(key=lambda l: (l.y0, -l.x1))
        return lines
