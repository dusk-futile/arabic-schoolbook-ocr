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
# A Latin reading replaces an Arabic one only above these. See _merge_latin.
LATIN_MIN_CONF = 0.80     # the Latin recogniser must be sure
LATIN_MIN_GAP = 0.20      # and must beat the Arabic reading by this margin
LATIN_STRONG_CONF = 0.85  # above this, a dictionary hit is not required
LATIN_STRONG_GAP = 0.30

PAD_RATIO = 0.75
PAD_MIN = 24
PAD_X = 24
MAX_CANVAS_H = 60000


class HybridEngine(OCREngine):
    name = "hybrid-dbnet-tesseract"

    def __init__(self, langs: str = "ara", timeout: int = 600,
                 latin_langs: str = "eng", mixed_script: bool = True):
        from rapidocr_onnxruntime import RapidOCR
        self.binary = find_binary()
        self.tessdata = find_tessdata(langs)
        if not self.binary or not self.tessdata:
            raise RuntimeError("Tesseract not available for the hybrid engine")
        self.langs = langs
        self.latin_langs = latin_langs
        self.mixed_script = mixed_script and bool(find_tessdata(latin_langs))
        self.timeout = timeout
        self._det = RapidOCR()
        self._lex = None

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

    # ------------------------------------------------------- mixed script
    @property
    def lexicon(self):
        if self._lex is None:
            from ..lexicon import Lexicon
            self._lex = Lexicon()
        return self._lex

    def _merge_latin(self, arabic: List[dict], latin: List[dict]) -> List[dict]:
        """Swap in the Latin reading wherever it is demonstrably the right one.

        Arabic and Latin need different recognisers and no single Tesseract
        model does both: `ara` cannot emit a Latin character at all (its
        alphabet has none), while `ara+eng` reads Latin but degrades Arabic.
        So each line is read twice and arbitrated per word - and arbitrated by
        a *dictionary*, not by comparing the two models' confidences, which are
        not on a common scale.

        A word is replaced only when the Latin reading is confidently better:
        the Latin recogniser is sure of it, it beats the Arabic reading by a
        clear margin, it is a real English word, and the Arabic reading is not
        a real Arabic word. The confidence margin is what does the work - a
        dictionary check alone swapped 123 words on a page containing 17, since
        Arabic forced through an English model lands on short English words
        constantly ("Goll", "Yoga", "Flag"). Those arrive at confidence 0.01 to
        0.26 while genuine Latin arrives at 0.92 to 0.95, so the two
        populations barely overlap.
        """
        if not latin:
            return arabic
        lex = self.lexicon
        if not lex.english:
            return arabic
        out, swapped = [], 0
        for w in arabic:
            ax0, ax1 = w["left"], w["left"] + w["width"]
            best, best_ov = None, 0.0
            for c in latin:
                # The two passes read the SAME stacked canvas, so a candidate
                # must sit on the same row as well as overlap horizontally.
                # Matching on x alone pairs words from different lines.
                if abs(c["top"] - w["top"]) > max(12, w["height"] * 0.6):
                    continue
                cx0, cx1 = c["left"], c["left"] + c["width"]
                inter = max(0, min(ax1, cx1) - max(ax0, cx0))
                narrower = max(1, min(ax1 - ax0, cx1 - cx0))
                ov = inter / narrower
                if ov > best_ov:
                    best, best_ov = c, ov
            if best is not None and best_ov > 0.55:
                cand = best["text"].strip()
                gap = best["conf"] - w["conf"]
                letters = [c for c in cand if c.isalpha()]
                latin_share = (sum(1 for c in letters if ord(c) < 0x0250)
                               / max(len(letters), 1))
                # A dictionary hit is sufficient but not necessary: most Latin
                # inside an Arabic book is proper nouns and technical terms
                # ("Wertheimer", "psychiologia", "WAIS") that no English
                # wordlist contains. The confidence margin carries those.
                credible = (lex.contains_en(cand)
                            or (best["conf"] >= LATIN_STRONG_CONF
                                and gap >= LATIN_STRONG_GAP))
                if (best["conf"] >= LATIN_MIN_CONF and gap >= LATIN_MIN_GAP
                        and latin_share >= 0.8 and len(cand) >= 3 and credible
                        and not lex.contains(w["text"].strip())):
                    nw = dict(w)
                    nw["text"] = cand
                    out.append(nw)
                    swapped += 1
                    continue
            out.append(w)
        self.latin_swaps = getattr(self, "latin_swaps", 0) + swapped
        return out

    def _tsv(self, img: np.ndarray, psm: int = 6, langs: Optional[str] = None) -> List[dict]:
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "stack.png")
            cv2.imwrite(path, img)
            env = dict(os.environ, TESSDATA_PREFIX=os.path.abspath(self.tessdata))
            proc = subprocess.run(
                [self.binary, path, "stdout", "-l", langs or self.langs,
                 "--psm", str(psm), "tsv"],
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
        if self.mixed_script:
            try:
                words = self._merge_latin(words, self._tsv(canvas, langs=self.latin_langs))
            except Exception:
                pass

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
