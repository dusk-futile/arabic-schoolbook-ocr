"""The learned paragraph-boundary classifier.

Eleven geometric features, logistic regression, about 1 KB of weights on disk.
It is used as a tiebreaker: the hand-written rules decide every boundary they
are confident about, and this model is consulted only where they are not.

Why this and not a language model. A local 1.5B and a 3B model were both tried
on exactly this decision and both answered the *same word to every case* -
"NEW" for all of them under an English prompt, "نعم" for all of them under an
Arabic one. They were following the framing of the question, not the evidence,
because the evidence is geometric: how much of the column the previous line
filled, and how big the vertical gap is. A language model handed two text
snippets cannot see that. This model is handed exactly that, costs
microseconds instead of seconds, and its weights can be read and argued with.

Training and leave-one-style-out validation live in eval/train_boundary.py.
"""
from __future__ import annotations

import json
import math
import os
from typing import List, Optional

MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "models", "boundary_lr.json")


class BoundaryModel:
    def __init__(self, path: str = MODEL_PATH):
        self.path = path
        self.weights: List[float] = []
        self.mean: List[float] = []
        self.std: List[float] = []
        self.features: List[str] = []
        self.threshold: float = 0.5
        self.meta: dict = {}
        if os.path.exists(path):
            try:
                d = json.load(open(path, encoding="utf-8"))
                self.weights = d["weights"]
                self.mean = d["mean"]
                self.std = d["std"]
                self.features = d.get("features", [])
                self.threshold = float(d.get("threshold", 0.5))
                self.meta = d.get("leave_one_style_out", {})
            except Exception:
                self.weights = []

    @property
    def available(self) -> bool:
        return bool(self.weights)

    def probability(self, feats: List[float]) -> Optional[float]:
        if not self.available or len(feats) != len(self.weights):
            return None
        z = 0.0
        for x, w, m, s in zip(feats, self.weights, self.mean, self.std):
            z += w * ((x - m) / (s if s > 1e-8 else 1.0))
        z = max(-40.0, min(40.0, z))
        return 1.0 / (1.0 + math.exp(-z))

    def is_break(self, feats: List[float]) -> Optional[bool]:
        p = self.probability(feats)
        return None if p is None else p >= self.threshold

    def explain(self, feats: List[float], top: int = 3) -> str:
        """The features that pushed this decision, for the review report."""
        if not self.available:
            return ""
        contrib = []
        for name, x, w, m, s in zip(self.features, feats, self.weights,
                                    self.mean, self.std):
            contrib.append((abs(w * ((x - m) / (s if s > 1e-8 else 1.0))), name))
        contrib.sort(reverse=True)
        return ",".join(n for _, n in contrib[:top])


_SINGLETON: Optional[BoundaryModel] = None


def get_model() -> BoundaryModel:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = BoundaryModel()
    return _SINGLETON
