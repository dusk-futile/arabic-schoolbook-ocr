"""Audit a .docx for the whitespace faults that ruin a Braille emboss.

A Braille embosser treats a space and a paragraph mark as completely different
instructions. A stray line break inside a paragraph becomes a hard line ending
in Braille; a double space becomes a real extra cell; a trailing space can push
a line past the cell count and wrap. So this checks the document structure
literally, at the XML level, rather than trusting how it looks in Word.
"""
from __future__ import annotations

import re
import sys
import zipfile
from collections import Counter

BAD_CHARS = {
    " ": "NO-BREAK SPACE",
    " ": "FIGURE SPACE",
    " ": "NARROW NO-BREAK SPACE",
    " ": "THIN SPACE",
    " ": "HAIR SPACE",
    " ": "LINE SEPARATOR",
    " ": "PARAGRAPH SEPARATOR",
    "\t": "TAB",
    "\v": "VERTICAL TAB",
    "\f": "FORM FEED",
    "​": "ZERO WIDTH SPACE",
    "‎": "LTR MARK",
    "‏": "RTL MARK",
    "‪": "LTR EMBEDDING",
    "‫": "RTL EMBEDDING",
    "‬": "POP DIRECTIONAL",
    "﻿": "BOM / ZWNBSP",
    "ـ": "TATWEEL",
}

FATAL = ["hard_line_breaks", "newline_inside_paragraph", "tab_runs",
         "double_space", "leading_or_trailing_space"]


def audit(path: str):
    import docx
    doc = docx.Document(path)
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")

    f = Counter()
    ex = {}

    def note(key, sample=""):
        f[key] += 1
        if key not in ex and sample:
            ex[key] = sample[:90]

    f["hard_line_breaks"] = len(re.findall(r"<w:br(?![a-zA-Z])(?![^>]*w:type=\"page\")", xml))
    f["page_breaks"] = len(re.findall(r"w:type=\"page\"", xml))
    f["tab_runs"] = len(re.findall(r"<w:tab\s*/>", xml))

    paras = doc.paragraphs
    f["paragraphs_total"] = len(paras)
    for p in paras:
        t = p.text
        if not t.strip():
            note("empty_paragraphs")
            continue
        if "\n" in t or "\r" in t:
            note("newline_inside_paragraph", repr(t))
        if "  " in t:
            note("double_space", t)
        if t != t.strip():
            note("leading_or_trailing_space", repr(t))
        if re.search(r"\s[،؛؟!\.:]", t):
            note("space_before_punctuation", t)
        for ch, name in BAD_CHARS.items():
            if ch in t:
                note("char:" + name, t)

    words = sum(len(p.text.split()) for p in paras)
    f["words_total"] = words
    f["avg_words_per_paragraph"] = round(words / max(len(paras), 1), 1)
    return f, ex


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "output/sample_book.docx"
    f, ex = audit(path)
    print("AUDIT  " + path)
    print("=" * 70)
    ok = True
    for k in FATAL:
        v = f.get(k, 0)
        if v:
            ok = False
        print("  [%s] %-34s %s" % ("FAIL" if v else " ok ", k, v))
        if v and k in ex:
            print("         e.g. " + ex[k])
    print("  " + "-" * 66)
    for k in sorted(f):
        if k in FATAL:
            continue
        print("         %-34s %s" % (k, f[k]))
        if k in ex:
            print("           e.g. " + ex[k])
    print("=" * 70)
    print("VERDICT:", "clean for embossing" if ok else "NEEDS FIXING")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
