"""OCR front-end producing the same ``Line`` objects as the digital front-end."""
from __future__ import annotations

import os
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np

from ..model import Line
from .ppocr_arabic import ArabicRecognizer, segment_words

from ..paths import MODELS_DIR  # noqa: F401


class OCREngine:
    name = "base"

    def page_lines(self, img_bgr, page_no: int, scale: float) -> List[Line]:
        raise NotImplementedError


class PPOCRArabic(OCREngine):
    """DBNet detection + word-segmented PP-OCR Arabic recognition."""

    name = "ppocr-arabic-v4"

    def __init__(self, model_dir: Optional[str] = None, threads: int = 0):
        from rapidocr_onnxruntime import RapidOCR

        model_dir = model_dir or os.path.join(MODELS_DIR, "arabic_v4")
        self._det = RapidOCR()
        self.rec = ArabicRecognizer(
            os.path.join(model_dir, "model.onnx"),
            os.path.join(model_dir, "arabic_dict.txt"),
            threads=threads,
        )
        self.timings = {"detect": 0.0, "recognise": 0.0}

    def detect(self, img_bgr) -> List[np.ndarray]:
        t = time.time()
        res, _ = self._det(img_bgr, use_det=True, use_cls=False, use_rec=False)
        self.timings["detect"] += time.time() - t
        if not res:
            return []
        return [np.array(b, dtype=np.float32) for b in res]

    def page_lines(self, img_bgr, page_no: int, scale: float) -> List[Line]:
        boxes = self.detect(img_bgr)
        if not boxes:
            return []
        H, W = img_bgr.shape[:2]
        crops, meta = [], []
        t = time.time()
        for b in boxes:
            x0, y0 = int(max(0, b[:, 0].min())), int(max(0, b[:, 1].min()))
            x1, y1 = int(min(W, b[:, 0].max())), int(min(H, b[:, 1].max()))
            if x1 - x0 < 8 or y1 - y0 < 8:
                continue
            pad = max(1, int((y1 - y0) * 0.06))
            crop = img_bgr[max(0, y0 - pad):min(H, y1 + pad), x0:x1]
            words = segment_words(crop)
            if not words:
                words = [(0, crop.shape[1])]
            base = len(crops)
            for a, bb in words:
                crops.append(crop[:, a:bb])
            meta.append((x0, y0, x1, y1, base, len(words)))
        results = self.rec.recognize(crops)
        self.timings["recognise"] += time.time() - t

        lines: List[Line] = []
        for (x0, y0, x1, y1, base, n) in meta:
            got = results[base:base + n]
            # RTL: the rightmost word on the line is read first
            ordered = list(reversed(got))
            text = " ".join(t for t, _ in ordered if t.strip())
            if not text.strip():
                continue
            confs = [c for t, c in ordered if t.strip()]
            lines.append(Line(
                text=text,
                bbox=(x0 / scale, y0 / scale, x1 / scale, y1 / scale),
                page=page_no,
                size=(y1 - y0) / scale * 0.78,
                conf=float(np.mean(confs)) if confs else 0.0,
                source="ocr",
            ))
        return lines


def _tesseract_factory(**kw):
    from .tesseract import TesseractEngine
    return TesseractEngine(**kw)


def _tesseract_auto(**kw):
    from .tesseract import TesseractEngine
    # psm 3 = full automatic page segmentation, including column detection.
    # psm 6 assumes one uniform block and shreds a two-column page.
    kw.setdefault("psm", 3)
    return TesseractEngine(**kw)


def _hybrid_factory(**kw):
    from .hybrid import HybridEngine
    return HybridEngine(**kw)


_REGISTRY = {
    "ppocr-arabic": PPOCRArabic,
    "tesseract": _tesseract_factory,
    "tesseract-auto": _tesseract_auto,
    "hybrid": _hybrid_factory,
}


def best_available(**kw) -> "OCREngine":
    """Prefer Tesseract when it is installed, otherwise the pure-pip engine.

    Measured on the same gold set: Tesseract has the same character error but
    roughly a third of the word error, and runs twice as fast. PP-OCR remains
    the floor because it needs no binary and therefore always works.
    """
    from . import tesseract as _t
    if _t.available():
        try:
            from .hybrid import HybridEngine
            return HybridEngine(**kw)
        except Exception:
            try:
                return _t.TesseractEngine(**kw)
            except Exception:
                pass
    return PPOCRArabic()


def available_engines() -> List[str]:
    return sorted(_REGISTRY)


def get_engine(name: str = "ppocr-arabic", **kw) -> OCREngine:
    if name not in _REGISTRY:
        raise ValueError(f"unknown OCR engine {name!r}; have {available_engines()}")
    return _REGISTRY[name](**kw)
