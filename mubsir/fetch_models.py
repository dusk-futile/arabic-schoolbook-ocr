"""One-time asset download. After this the tool never touches the network.

Kept out of version control on purpose: model weights and dictionaries are
large and separately licensed. Copy the whole `models/` folder to move an
installation onto an offline machine.
"""
from __future__ import annotations

import gzip
import os
import re
import sys
import urllib.request

from mubsir.paths import MODELS_DIR as MODELS, PKG_DIR

ROOT = os.path.dirname(PKG_DIR)
UA = {"User-Agent": "mubsir/0.2 (+offline Arabic OCR)"}

BINARIES = [
    ("arabic_v4/model.onnx",
     "https://huggingface.co/cycloneboy/arabic_PP-OCRv4_rec_infer/resolve/main/model.onnx"),
    ("arabic_v4/arabic_dict.txt",
     "https://huggingface.co/cycloneboy/arabic_PP-OCRv4_rec_infer/resolve/main/arabic_dict.txt"),
    ("tessdata_best/ara.traineddata",
     "https://github.com/tesseract-ocr/tessdata_best/raw/main/ara.traineddata"),
]

# Word lists, fetched from URLs rather than the OS so Windows behaves the same.
LEXICONS = [
    ("lexicon/ar_words.txt.gz",
     "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/ar/ar.dic",
     "arabic"),
    ("lexicon/en_words.txt.gz",
     "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/en/en_US.dic",
     "latin"),
]


def _get(url: str, timeout: int = 600) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_binary(rel: str, url: str) -> bool:
    dest = os.path.join(MODELS, rel)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"  have  {rel}")
        return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"  get   {rel} ...", end="", flush=True)
    try:
        data = _get(url)
        with open(dest, "wb") as f:
            f.write(data)
        print(f" {len(data)//1024} KB")
        return True
    except Exception as e:
        print(f" FAILED: {e}")
        return False


def build_lexicon(rel: str, url: str, script: str) -> bool:
    dest = os.path.join(MODELS, rel)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"  have  {rel}")
        return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"  build {rel} ...", end="", flush=True)
    try:
        raw = _get(url).decode("utf-8", "replace")
    except Exception as e:
        print(f" FAILED: {e}")
        return False
    sys.path.insert(0, ROOT)
    from mubsir.arabic import canonical, strip_tashkeel

    words = set()
    for line in raw.split("\n")[1:]:
        w = line.split("/")[0].strip()
        if not w:
            continue
        if script == "arabic":
            w = strip_tashkeel(canonical(w))
            if len(w) > 1 and all(0x0600 <= ord(c) <= 0x06FF for c in w):
                words.add(w)
        else:
            w = w.lower()
            if 2 <= len(w) <= 20 and re.fullmatch(r"[a-z]+", w):
                words.add(w)
    with gzip.open(dest, "wt", encoding="utf-8") as f:
        f.write("\n".join(sorted(words)))
    print(f" {len(words)} words, {os.path.getsize(dest)//1024} KB")
    return True


def copy_tess_configs() -> None:
    """Tesseract needs its `configs/` folder beside the traineddata to emit TSV."""
    import shutil
    dest = os.path.join(MODELS, "tessdata_best", "configs")
    if os.path.isdir(dest):
        return
    for cand in [os.path.join(ROOT, ".mm-tess", "share", "tessdata", "configs"),
                 os.path.join(ROOT, ".mm-tess", "Library", "share", "tessdata", "configs")]:
        if os.path.isdir(cand):
            shutil.copytree(cand, dest)
            print("  copied tesseract configs")
            return
    print("  note: tesseract configs not found; the hybrid engine needs them.")


def main() -> int:
    print("Downloading models and dictionaries (once, ~30 MB).")
    ok = True
    for rel, url in BINARIES:
        ok &= fetch_binary(rel, url)
    for rel, url, script in LEXICONS:
        build_lexicon(rel, url, script)      # optional, never fatal
    copy_tess_configs()
    print("Done." if ok else "Some downloads failed; re-run to retry.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
