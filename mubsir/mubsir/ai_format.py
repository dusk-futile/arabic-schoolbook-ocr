"""A small local model, used for formatting decisions only.

The brief's rule stands: a hallucinated word in a Braille book is worse than a
garbled one, because the reader has no way to detect it. So this module is
built so that inventing text is not merely discouraged but *structurally
impossible* - no text is ever taken from the model.

The model is asked one closed question, about a boundary the deterministic
engine was already unsure of:

    "Are these two lines the same paragraph, or two paragraphs?"

It answers with a single token. The answer moves a paragraph boundary. The
words themselves are never sent back into the document, so the worst a bad
answer can do is join or split a paragraph - visible, reviewable, and exactly
the class of mistake a human proofreader catches in seconds.

It runs only on boundaries the scorer flagged as uncertain, which on a real
book is a few dozen calls rather than thousands, and it degrades to a no-op
when Ollama is not installed.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
PREFERRED_MODELS = ["qwen2.5:1.5b", "qwen2.5:3b", "gemma2:2b", "qwen2.5vl:3b"]

# Deliberately terse. A long prompt costs CPU seconds per call and buys nothing
# on a binary question.
SYSTEM = (
    "You judge Arabic book typography. Given the end of one line and the start "
    "of the next, answer whether they belong to the SAME paragraph or to TWO "
    "different paragraphs. Answer with exactly one word: SAME or NEW."
)

PROMPT = (
    "End of line A:\n{a}\n\n"
    "Start of line B:\n{b}\n\n"
    "Line A filled {fill:.0%} of the column width.\n"
    "Answer SAME or NEW."
)


@dataclass
class AIDecision:
    index: int
    before: str
    after: str
    answer: str
    applied: bool
    reason: str = ""


@dataclass
class AIFormatter:
    host: str = DEFAULT_HOST
    model: Optional[str] = None
    timeout: int = 30
    max_calls: int = 400
    decisions: List[AIDecision] = field(default_factory=list)
    _calls: int = 0

    # ------------------------------------------------------------- discovery
    def __post_init__(self) -> None:
        if self.model is None:
            self.model = self._pick_model()

    def _get_json(self, path: str) -> Optional[dict]:
        try:
            with urllib.request.urlopen(f"{self.host}{path}", timeout=4) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            return None

    def _pick_model(self) -> Optional[str]:
        tags = self._get_json("/api/tags")
        if not tags:
            return None
        have = {m.get("name", "") for m in tags.get("models", [])}
        for want in PREFERRED_MODELS:
            if want in have:
                return want
        return next(iter(have), None) or None

    @property
    def available(self) -> bool:
        return bool(self.model)

    # ----------------------------------------------------------------- call
    def _ask(self, a: str, b: str, fill: float) -> Optional[str]:
        if not self.model or self._calls >= self.max_calls:
            return None
        payload = {
            "model": self.model,
            "system": SYSTEM,
            "prompt": PROMPT.format(a=a[-160:], b=b[:160], fill=fill),
            "stream": False,
            # Greedy and capped: this is a classifier, not a writer.
            "options": {"temperature": 0.0, "num_predict": 4, "top_k": 1},
        }
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = json.loads(r.read().decode("utf-8"))
        except Exception:
            return None
        self._calls += 1
        text = (out.get("response") or "").strip().upper()
        if "NEW" in text:
            return "NEW"
        if "SAME" in text:
            return "SAME"
        return None          # anything else is discarded, never guessed at

    # -------------------------------------------------------------- public
    def adjudicate(self, pairs: List[Tuple[int, str, str, float, bool]]
                   ) -> dict:
        """pairs: (index, tail_of_A, head_of_B, fill_ratio, engine_said_break).

        Returns {index: is_break} containing ONLY the boundaries the model
        actually changed. Everything else keeps the deterministic answer.
        """
        overrides: dict = {}
        if not self.available:
            return overrides
        for idx, a, b, fill, engine_break in pairs:
            answer = self._ask(a, b, fill)
            if answer is None:
                self.decisions.append(
                    AIDecision(idx, a[-40:], b[:40], "?", False, "no usable answer"))
                continue
            wants_break = (answer == "NEW")
            if wants_break == engine_break:
                self.decisions.append(
                    AIDecision(idx, a[-40:], b[:40], answer, False, "agreed"))
                continue
            overrides[idx] = wants_break
            self.decisions.append(
                AIDecision(idx, a[-40:], b[:40], answer, True, "overrode engine"))
        return overrides

    def summary(self) -> dict:
        return {
            "model": self.model,
            "calls": self._calls,
            "changed": sum(1 for d in self.decisions if d.applied),
            "agreed": sum(1 for d in self.decisions if d.reason == "agreed"),
            "unusable": sum(1 for d in self.decisions if d.reason == "no usable answer"),
        }
