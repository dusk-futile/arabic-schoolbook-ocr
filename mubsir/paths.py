"""Where things live.

Everything the tool needs sits inside the package, so the repository root holds
only the readme, the licence, the picture, the requirements and the launcher.
One module owns these paths so moving them again is a one-line change rather
than a hunt through five files.
"""
from __future__ import annotations

import os

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(PKG_DIR, "models")
LEXICON_DIR = os.path.join(MODELS_DIR, "lexicon")
TESSDATA_DIR = os.path.join(MODELS_DIR, "tessdata_best")
PPOCR_DIR = os.path.join(MODELS_DIR, "arabic_v4")

# Written next to wherever the user is working, not inside the package.
CWD = os.getcwd()
INPUT_DIR = os.path.join(CWD, "input")
OUTPUT_DIR = os.path.join(CWD, "output")
