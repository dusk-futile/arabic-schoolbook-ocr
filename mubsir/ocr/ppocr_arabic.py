"""Arabic OCR on CPU: DBNet line detection + PP-OCR Arabic recognition.

The important discovery encoded here is that PP-OCR recognition models are
trained on short crops and collapse on a full justified book line (~30:1
aspect). Recognising whole lines yields ~67% CER; segmenting each line into
words on the whitespace projection first and recognising those brings it to a
few percent. So the pipeline is deliberately: detect line -> split to words ->
recognise words -> reassemble right-to-left.

Total model weight is about 12 MB, which is what makes this viable on an
8 GB machine with no GPU and no admin rights.
"""
from __future__ import annotations

import os
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np
import onnxruntime as ort

REC_H = 48
MAX_REC_W = 1600
MIN_WORD_PX = 6
BATCH = 8


class ArabicRecognizer:
    def __init__(self, model_path: str, dict_path: str, threads: int = 0):
        opts = ort.SessionOptions()
        if threads:
            opts.intra_op_num_threads = threads
        self.sess = ort.InferenceSession(
            model_path, sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self.iname = self.sess.get_inputs()[0].name
        raw = open(dict_path, encoding="utf-8").read().split("\n")
        if raw and raw[-1] == "":
            raw = raw[:-1]
        # PP-OCR convention: index 0 is the CTC blank, a space is appended last
        self.chars = ["\x00"] + raw + [" "]

    def _prep(self, crop: np.ndarray, target_w: int) -> np.ndarray:
        h, w = crop.shape[:2]
        w_scaled = max(8, min(int(round(REC_H * w / max(h, 1))), target_w))
        img = cv2.resize(crop, (w_scaled, REC_H), interpolation=cv2.INTER_LINEAR)
        norm = (img.astype(np.float32) / 255.0 - 0.5) / 0.5
        # Pad in NORMALISED space with 0.0 (mid-grey). Padding the uint8 image
        # with zeros would paint black, which the recogniser reads as ink and
        # which produces phantom repeated characters.
        canvas = np.zeros((REC_H, target_w, 3), np.float32)
        canvas[:, :w_scaled] = norm
        return canvas.transpose(2, 0, 1)

    def recognize(self, crops: Sequence[np.ndarray]) -> List[Tuple[str, float]]:
        if not crops:
            return []
        out: List[Tuple[str, float]] = []
        order = sorted(range(len(crops)), key=lambda i: crops[i].shape[1] / max(crops[i].shape[0], 1))
        results: dict = {}
        for s in range(0, len(order), BATCH):
            idxs = order[s:s + BATCH]
            tw = max(
                16,
                min(MAX_REC_W, max(int(round(REC_H * crops[i].shape[1] / max(crops[i].shape[0], 1)))
                                   for i in idxs)),
            )
            tw = int(np.ceil(tw / 8) * 8)
            batch = np.stack([self._prep(crops[i], tw) for i in idxs])
            logits = self.sess.run(None, {self.iname: batch})[0]
            for k, i in enumerate(idxs):
                results[i] = self._ctc(logits[k])
        for i in range(len(crops)):
            out.append(results.get(i, ("", 0.0)))
        return out

    def _ctc(self, probs: np.ndarray) -> Tuple[str, float]:
        idx = probs.argmax(1)
        conf = probs.max(1)
        chars: List[str] = []
        scores: List[float] = []
        prev = 0
        for i, c in zip(idx, conf):
            if i != 0 and i != prev:
                if i < len(self.chars):
                    chars.append(self.chars[i])
                    scores.append(float(c))
            prev = i
        return "".join(chars), (float(np.mean(scores)) if scores else 0.0)


def _otsu_1d(values: List[int]) -> float:
    """Two-cluster split point on a 1-D list. Used on gap widths."""
    if len(values) < 2:
        return 0.0
    vs = sorted(values)
    best_t, best_var = vs[0], -1.0
    total = len(vs)
    for i in range(1, total):
        if vs[i] == vs[i - 1]:
            continue
        a, b = vs[:i], vs[i:]
        wa, wb = len(a) / total, len(b) / total
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        var = wa * wb * (ma - mb) ** 2
        if var > best_var:
            best_var, best_t = var, (vs[i - 1] + vs[i]) / 2
    return best_t


def segment_words(line_bgr: np.ndarray, min_gap_ratio: float = 0.0) -> List[Tuple[int, int]]:
    """Split a line image at inter-word whitespace.

    Arabic joins letters inside a word, so real word gaps are markedly wider
    than intra-word letter gaps - a genuinely bimodal distribution. The split
    point is therefore found per-line with a 1-D Otsu on the gap widths rather
    than a fixed fraction of line height, because the fixed ratio breaks as
    soon as font size, tracking or justification stretch changes.
    """
    if line_bgr.size == 0:
        return []
    gray = cv2.cvtColor(line_bgr, cv2.COLOR_BGR2GRAY) if line_bgr.ndim == 3 else line_bgr
    bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    col = (bw > 0).sum(axis=0)
    h = line_bgr.shape[0]

    runs: List[Tuple[int, int]] = []
    start: Optional[int] = None
    for i, v in enumerate(col):
        if v == 0:
            if start is None:
                start = i
        else:
            if start is not None:
                runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(col)))
    # ignore the margins - only interior gaps carry word information
    interior = [(a, b) for a, b in runs if a > 0 and b < len(col)]
    if not interior:
        return [(0, len(col))] if (bw > 0).any() else []

    widths = [b - a for a, b in interior]
    floor = max(2.0, h * 0.06)
    if len(widths) >= 3:
        t = _otsu_1d(widths)
        thresh = max(floor, t)
        # if the split is degenerate the line is probably a single word
        if thresh >= max(widths):
            thresh = floor
    else:
        thresh = max(floor, h * (min_gap_ratio or 0.25))

    cuts = [0] + [(a + b) // 2 for a, b in interior if (b - a) >= thresh] + [len(col)]
    words: List[Tuple[int, int]] = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a < MIN_WORD_PX:
            continue
        if (bw[:, a:b] > 0).sum() < 20:
            continue
        words.append((a, b))
    return words or [(0, len(col))]
