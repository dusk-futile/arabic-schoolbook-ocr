"""Image clean-up before OCR.

Preprocessing usually moves CER more than swapping recognisers does, so this
runs by default on the scanned path. Every step is conservative: a step that
might destroy real ink is skipped rather than risked.
"""
from __future__ import annotations

from typing import Tuple

import cv2
import numpy as np


def to_gray(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def estimate_skew(img: np.ndarray, max_angle: float = 8.0) -> float:
    """Skew angle in degrees, from the projection profile variance.

    Text lines produce sharp horizontal ink peaks only when they are level, so
    the angle that maximises row-variance is the deskew angle.
    """
    g = to_gray(img)
    h, w = g.shape[:2]
    scale = 800.0 / max(h, w)
    if scale < 1.0:
        g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + 0.25, 0.25):
        m = cv2.getRotationMatrix2D((bw.shape[1] / 2, bw.shape[0] / 2), angle, 1.0)
        rot = cv2.warpAffine(bw, m, (bw.shape[1], bw.shape[0]),
                             flags=cv2.INTER_NEAREST, borderValue=0)
        proj = rot.sum(axis=1, dtype=np.float64)
        score = float(np.var(proj))
        if score > best_score:
            best_score, best_angle = score, float(angle)
    return best_angle


def deskew(img: np.ndarray, angle: float | None = None) -> Tuple[np.ndarray, float]:
    a = estimate_skew(img) if angle is None else angle
    if abs(a) < 0.15:
        return img, 0.0
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
    border = cv2.BORDER_REPLICATE
    out = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=border)
    return out, a


def remove_border(img: np.ndarray, max_frac: float = 0.06) -> np.ndarray:
    """Trim scanner black borders without ever eating into text."""
    g = to_gray(img)
    bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    h, w = bw.shape
    lim_y, lim_x = int(h * max_frac), int(w * max_frac)
    rows = (bw > 0).sum(1)
    cols = (bw > 0).sum(0)
    top = next((i for i in range(lim_y) if rows[i] < w * 0.6), 0)
    bot = next((i for i in range(lim_y) if rows[h - 1 - i] < w * 0.6), 0)
    left = next((i for i in range(lim_x) if cols[i] < h * 0.6), 0)
    right = next((i for i in range(lim_x) if cols[w - 1 - i] < h * 0.6), 0)
    if top or bot or left or right:
        return img[top:h - bot if bot else h, left:w - right if right else w]
    return img


def denoise(img: np.ndarray) -> np.ndarray:
    g = to_gray(img)
    return cv2.medianBlur(g, 3)


def prepare(img: np.ndarray, do_deskew: bool = True, do_border: bool = True) -> Tuple[np.ndarray, dict]:
    notes = {}
    out = img
    if do_border:
        before = out.shape
        out = remove_border(out)
        if out.shape != before:
            notes["border_trimmed"] = True
    if do_deskew:
        out, a = deskew(out)
        if a:
            notes["deskew_deg"] = round(a, 2)
    if out.ndim == 2:
        out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
    return out, notes
