"""Rebuild models/lexicon/en_words.txt.gz.

Source: the `web2` wordlist (Webster's Second International, 1934, public
domain), shipped as /usr/share/dict/words on macOS and BSD. Used only to
resolve damaged Latin glyphs inside Arabic documents.
"""
import gzip, os, re, sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "/usr/share/dict/words"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "models", "lexicon", "en_words.txt.gz")
if not os.path.exists(SRC):
    raise SystemExit(f"no wordlist at {SRC}; pass one as an argument")
words = {w.strip().lower() for w in open(SRC, encoding="utf-8", errors="replace")}
words = {w for w in words if 2 <= len(w) <= 20 and re.fullmatch(r"[a-z]+", w)}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with gzip.open(OUT, "wt", encoding="utf-8") as f:
    f.write("\n".join(sorted(words)))
print(f"{len(words)} words -> {OUT} ({os.path.getsize(OUT)//1024} KB)")
