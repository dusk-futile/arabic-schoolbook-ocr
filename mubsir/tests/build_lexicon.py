"""Rebuild models/lexicon/ar_words.txt.gz from the LibreOffice Arabic hunspell
dictionary. Run once, online; the result is bundled and used offline."""
import gzip, os, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
from mubsir.arabic import canonical, strip_tashkeel

URL = "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/ar/ar.dic"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "models", "lexicon", "ar_words.txt.gz")

req = urllib.request.Request(URL, headers={"User-Agent": "mubsir/0.1"})
raw = urllib.request.urlopen(req, timeout=300).read().decode("utf-8", "replace")
words = set()
for line in raw.split("\n")[1:]:
    w = strip_tashkeel(canonical(line.split("/")[0].strip()))
    if len(w) > 1 and all(0x0600 <= ord(c) <= 0x06FF for c in w):
        words.add(w)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with gzip.open(OUT, "wt", encoding="utf-8") as f:
    f.write("\n".join(sorted(words)))
print(f"{len(words)} stems -> {OUT} ({os.path.getsize(OUT)//1024} KB)")
