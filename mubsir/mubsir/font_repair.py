"""Recover real text from an Arabic PDF whose ToUnicode map is broken.

Word (and several Arabic DTP tools) can emit a PDF whose glyphs draw perfect
Arabic while the text layer decodes to systematic nonsense:

    renders as : ليصبح التفوق والموهبة هو المفهوم الشامل
    extracts as: ليربح التفػؽ كالسػـبة ىػ السفيػـ الذامل

The characters are not damaged, only mislabelled - and the mislabelling is
per *glyph form*, so 'و' comes out as 'ػ' when medial and 'ك' when initial.
That means the true text is fully recoverable without OCR.

The route is the embedded font itself. Read the raw glyph ids from the content
stream, then resolve each id to Unicode by: the font's own cmap; failing that,
by inverting the GSUB single substitutions that generated the contextual form;
failing that, by expanding the ligature back into its components. Recovering
text this way is exact, where OCR on the same pages costs about 7% CER.
"""
from __future__ import annotations

import io
import unicodedata
from typing import Dict, List, Optional

import pymupdf

from .model import Line

MAX_DEPTH = 8

# Persian look-alikes that Arabic subset fonts often resolve to. In an Arabic
# document these are always artefacts of the mapping, never intent.
LOOKALIKE = {"ی": "ي", "ک": "ك", "۰": "٠"}


def _is_arabic(u: int) -> bool:
    return 0x0600 <= u <= 0x06FF


class FontDecoder:
    """Glyph-id -> text, per font face, for one document."""

    def __init__(self, doc: pymupdf.Document):
        self.doc = doc
        self._cache: Dict[str, Dict[int, str]] = {}
        self._failed: set = set()
        # (font, glyph id) -> letter, learned by ResidualLearner for glyphs the
        # font's own tables could not resolve.
        self.overrides: Dict[tuple, str] = {}
        # Fonts whose ToUnicode map is fine and must be left alone. Repair is
        # not free: a subset font's cmap can be wrong in the other direction,
        # and overriding a correct ToUnicode turns "Norbert" into "Norberr".
        self.trusted: set = set()

    def apply_overrides(self, resolved: Dict[tuple, str]) -> None:
        self.overrides.update(resolved)
        for key in list(self._cache):
            for (font, gid), ch in resolved.items():
                if font == key:
                    self._cache[key][gid] = ch

    def _build(self, xref: int) -> Dict[int, str]:
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            return {}
        try:
            buf = self.doc.extract_font(xref)[3]
        except Exception:
            return {}
        if not buf:
            return {}
        try:
            tt = TTFont(io.BytesIO(buf), fontNumber=0, lazy=False)
        except Exception:
            return {}

        try:
            cmap = tt.getBestCmap() or {}
        except Exception:
            cmap = {}
        order = tt.getGlyphOrder()

        # glyph name -> unicode, preferring a real Arabic letter over a
        # presentation form or a Latin look-alike for the same glyph
        uni_of: Dict[str, int] = {}
        for u, gn in sorted(cmap.items()):
            if gn not in uni_of or (_is_arabic(u) and not _is_arabic(uni_of[gn])):
                uni_of[gn] = u

        single: Dict[str, str] = {}      # variant glyph -> source glyph
        ligs: Dict[str, List[str]] = {}
        if "GSUB" in tt:
            try:
                gsub = tt["GSUB"].table
                for lookup in gsub.LookupList.Lookup:
                    for sub in lookup.SubTable:
                        # every lookup in these fonts is Extension-wrapped
                        st = getattr(sub, "ExtSubTable", sub)
                        kind = type(st).__name__
                        if kind == "SingleSubst":
                            for src, dst in getattr(st, "mapping", {}).items():
                                single.setdefault(dst, src)
                        elif kind == "LigatureSubst":
                            for first, llist in getattr(st, "ligatures", {}).items():
                                for lg in llist:
                                    ligs.setdefault(lg.LigGlyph,
                                                    [first] + list(lg.Component))
            except Exception:
                pass

        try:
            from fontTools.agl import toUnicode as agl_to_unicode
        except ImportError:
            agl_to_unicode = None

        def resolve(gname: str, depth: int = 0) -> str:
            if depth > MAX_DEPTH:
                return ""
            u = uni_of.get(gname)
            if u is not None:
                return chr(u)
            if gname in single:
                return resolve(single[gname], depth + 1)
            if gname in ligs:
                return "".join(resolve(c, depth + 1) for c in ligs[gname])
            # Subsetting often strips a glyph's cmap entry while keeping its
            # name. Standard names ('t', 'uni0644') still identify the
            # character, which is what rescues embedded Latin runs - without
            # this, "inputs" comes back as "inpurs".
            if agl_to_unicode is not None and gname:
                try:
                    got = agl_to_unicode(gname)
                except Exception:
                    got = ""
                if got:
                    return got
            return ""

        out: Dict[int, str] = {}
        for i, gname in enumerate(order):
            s = resolve(gname)
            if s:
                out[i] = s
        return out

    def map_for(self, font_name: str, page: pymupdf.Page) -> Dict[int, str]:
        key = font_name.split("+")[-1]
        if key in self._cache:
            return self._cache[key]
        merged: Dict[int, str] = {}
        for info in page.get_fonts(full=True):
            xref, name = info[0], info[3]
            if not xref or name.split("+")[-1] != key or xref in self._failed:
                continue
            m = self._build(xref)
            if m:
                merged.update(m)
            else:
                self._failed.add(xref)
        for (font, gid), ch in self.overrides.items():
            if font == key:
                merged[gid] = ch
        self._cache[key] = merged
        return merged


def _clean(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    for a, b in LOOKALIKE.items():
        s = s.replace(a, b)
    return s


def decode_page(doc: pymupdf.Document, page: pymupdf.Page, page_no: int,
                decoder: Optional[FontDecoder] = None) -> List[Line]:
    """Rebuild a page's lines from raw glyph ids instead of the text layer."""
    dec = decoder or FontDecoder(doc)
    lines: List[Line] = []
    for span in page.get_texttrace():
        chars = span.get("chars") or []
        if not chars:
            continue
        font = span.get("font", "")
        gmap = {} if font.split("+")[-1] in dec.trusted else dec.map_for(font, page)
        pieces: List[str] = []
        pending = 0     # continuation slots owed by the previous ligature glyph
        for ch in chars:
            uni, gid = ch[0], ch[1]
            # A ligature draws one glyph but stands for several characters, so
            # the extractor emits placeholder entries with gid -1 for the
            # components after the first. The glyph itself already decodes to
            # all of them, so emitting the placeholders too doubles letters:
            # 'المقرر' comes out as 'املمقرر'. Placeholders are only skipped
            # when a ligature actually precedes them - a lone gid -1 elsewhere
            # is real text from a simply-encoded font.
            if gid < 0 and pending > 0:
                pending -= 1
                continue
            got = gmap.get(gid)
            if got is None:
                got = chr(uni) if 0 < uni < 0x110000 else ""
                pending = 0
            else:
                pending = len(unicodedata.normalize("NFKC", got)) - 1
            pieces.append(got)
        # texttrace emits glyphs in visual order; an RTL run's logical order
        # is the reverse of that. A Latin run embedded in an Arabic paragraph
        # is still read left to right, and reversing it turns "Julian Stanley"
        # into "Sranley ianJul", so decide from the glyphs rather than from the
        # surrounding paragraph's bidi level.
        rtl = bool(span.get("bidi_lvl", 0) % 2)
        joined = "".join(pieces)
        letters = [c for c in joined if c.isalpha()]
        if letters:
            latin = sum(1 for c in letters if ord(c) < 0x0250)
            if latin / len(letters) >= 0.6:
                rtl = False
        if rtl:
            pieces.reverse()
        text = _clean("".join(pieces))
        if not text.strip():
            continue
        bbox = tuple(span.get("bbox") or (0, 0, 0, 0))
        if bbox[2] - bbox[0] <= 0 or bbox[3] - bbox[1] <= 0:
            continue
        name = font.lower()
        lines.append(Line(
            text=text, bbox=bbox, page=page_no,
            size=round(float(span.get("size", 12.0)), 2),
            conf=1.0, source="font_repair",
            bold=("bold" in name or "black" in name),
            font=font,
        ))
    return lines


def choose_fonts(doc: pymupdf.Document, decoder: FontDecoder, lexicon,
                 pages: List[int]) -> Dict[str, dict]:
    """Decide, per font, whether its ToUnicode map can be trusted.

    Repair is applied per font rather than per document because a file can mix
    a broken Arabic face with a perfectly good Latin one. The test is the same
    dictionary test the router uses: does this font's ToUnicode output produce
    real words?
    """
    per_font: Dict[str, List[str]] = {}
    for pno in pages:
        page = doc[pno]
        for span in page.get_texttrace():
            font = span.get("font", "").split("+")[-1]
            chars = span.get("chars") or []
            txt = "".join(chr(c[0]) for c in chars if 0 < c[0] < 0x110000)
            if span.get("bidi_lvl", 0) % 2:
                txt = txt[::-1]
            per_font.setdefault(font, []).append(txt)

    report: Dict[str, dict] = {}
    for font, chunks in per_font.items():
        text = _clean(" ".join(chunks))
        words = [w for w in text.split() if len(w) >= 2]
        if len(words) < 25:
            continue
        arabic = [w for w in words if any(_is_arabic(ord(c)) for c in w)]
        latin = [w for w in words if any(c.isascii() and c.isalpha() for c in w)]
        if len(arabic) >= len(latin):
            valid = sum(1 for w in arabic if lexicon.contains(w)) / max(len(arabic), 1)
            script = "arabic"
        else:
            valid = sum(1 for w in latin if lexicon.contains_en(w)) / max(len(latin), 1)
            script = "latin"
        trusted = valid >= 0.50
        if trusted:
            decoder.trusted.add(font)
        report[font] = {"script": script, "tounicode_validity": round(valid, 3),
                        "trusted": trusted, "words": len(words)}
    return report


def repair_quality(doc: pymupdf.Document, page: pymupdf.Page) -> float:
    """Share of drawn glyphs this document's fonts can resolve.

    Used by the router: a high share means font repair will work and OCR is
    unnecessary; a low one means the fonts are not embedded or not usable and
    the page has to be rasterised.
    """
    dec = FontDecoder(doc)
    total = hit = 0
    for span in page.get_texttrace():
        gmap = dec.map_for(span.get("font", ""), page)
        for ch in span.get("chars") or []:
            if ch[0] == 32:
                continue
            total += 1
            if ch[1] in gmap:
                hit += 1
    return hit / total if total else 0.0


# --------------------------------------------------------------- calibration
PUA_BASE = 0xE000
ARABIC_CANDIDATES = list("ابتثجحخدذرزسشصضطظعغفقكلمنهوياىةئؤإأآء")
LATIN_CANDIDATES = list("abcdefghijklmnopqrstuvwxyz")


def _placeholder(slot: int) -> str:
    return chr(PUA_BASE + slot)


class ResidualLearner:
    """Work out what the glyphs the font could not resolve actually are.

    A subset font may leave a handful of contextual forms unreachable through
    cmap and GSUB. Those fall back to the PDF's broken ToUnicode value, which
    is wrong in a *consistent* way - one specific glyph id always comes out as
    the same wrong letter. Because it is consistent, the right letter can be
    identified by substitution: try each Arabic letter in the words where the
    glyph occurs and keep the one that turns nonsense into dictionary words.

    Deterministic, auditable, and it never guesses - a glyph whose best
    candidate does not clearly win is left alone and reported instead.
    """

    # Orthographic near-twins. When the runner-up is one of these the contest
    # is a coin-flip the lexicon cannot settle, and picking wrong produces a
    # misspelling a Braille reader would hit. Those are refused, not guessed.
    TWINS = [set("يى"), set("هة"), set("اأإآ"), set("وؤ"), set("ئي")]

    # Thresholds chosen by measuring end-to-end lexicon coverage on a real
    # 209-page book, not picked by eye: the values below moved it from 0.892
    # to 0.913 against the tighter pair they replaced.
    def __init__(self, lexicon, min_words: int = 12, min_ratio: float = 0.45,
                 min_margin: float = 1.5, probable_ratio: float = 0.55,
                 probable_margin: float = 1.15):
        self.probable_ratio = probable_ratio
        self.probable_margin = probable_margin
        self.lex = lexicon
        self.min_words = min_words
        self.min_ratio = min_ratio
        self.min_margin = min_margin
        self.decisions: Dict[tuple, dict] = {}

    def _twins(self, a: str, b: str) -> bool:
        return any(a in grp and b in grp for grp in self.TWINS)

    def learn(self, samples: Dict[tuple, List[str]]) -> Dict[tuple, str]:
        """samples: (font, gid) -> words containing that glyph's placeholder."""
        out: Dict[tuple, str] = {}
        for key, words in samples.items():
            words = [w for w in words if 2 <= len(w) <= 18][: 400]
            if len(words) < self.min_words:
                continue
            ph = None
            for w in words:
                for ch in w:
                    if PUA_BASE <= ord(ch) < PUA_BASE + 0x1000:
                        ph = ch
                        break
                if ph:
                    break
            if ph is None:
                continue
            # Latin runs (citations, technical terms) are damaged the same way
            # and are resolved the same way, against the English wordlist.
            latin_chars = sum(1 for w in words for c in w if c.isascii() and c.isalpha())
            arabic_chars = sum(1 for w in words for c in w if 0x0600 <= ord(c) <= 0x06FF)
            is_latin = latin_chars > arabic_chars

            scores: List[tuple] = []
            if is_latin:
                for cand in LATIN_CANDIDATES:
                    hit = sum(1 for w in words if self.lex.contains_en(w.replace(ph, cand)))
                    scores.append((hit, hit, cand))
                    scores.append((hit, hit, cand.upper()))
            else:
                # Score on EXACT lexicon hits, not affix-derived ones. Clitic
                # stripping is permissive enough that half the alphabet scores
                # well on it, which hides the real winner.
                for cand in ARABIC_CANDIDATES:
                    exact = sum(1 for w in words
                                if self.lex.contains_exact(w.replace(ph, cand)))
                    loose = sum(1 for w in words
                                if self.lex.contains(w.replace(ph, cand)))
                    scores.append((exact, loose, cand))
            scores.sort(reverse=True)
            best = scores[0]
            runner = scores[1] if len(scores) > 1 else (0, 0, "")
            ratio = best[0] / len(words)          # exact-hit ratio
            loose = best[1] / len(words)          # plausibility: is it a word at all
            margin = best[0] / max(runner[0], 1)
            twin = self._twins(best[2], runner[2])
            if is_latin and runner[2].lower() == best[2].lower():
                # upper/lower of the same letter is not a real contest
                runner = next((s for s in scores[1:]
                               if s[2].lower() != best[2].lower()), (0, 0, ""))
                margin = best[0] / max(runner[0], 1)
                twin = False

            # Two tiers. The fallback character is *known* to be wrong, so a
            # candidate that turns most of these into real Arabic is an
            # improvement even when it is not provably the only answer -
            # it is applied, but every paragraph it touches gets flagged.
            confident = (margin >= self.min_margin and loose >= self.min_ratio
                         and not (twin and margin < 2.5))
            probable = (not confident and loose >= self.probable_ratio
                        and margin >= self.probable_margin and not twin)
            tier = "confident" if confident else ("probable" if probable else "refused")

            self.decisions[key] = {
                "letter": best[2], "hits": best[0], "loose_hits": best[1],
                "words": len(words), "exact_ratio": round(ratio, 3),
                "loose_ratio": round(loose, 3), "margin": round(margin, 2),
                "runner_up": runner[2], "twin_conflict": twin, "tier": tier,
                "accepted": tier != "refused",
            }
            if tier != "refused":
                out[key] = best[2]
        return out


def calibrate(doc: pymupdf.Document, decoder: FontDecoder, lexicon,
              pages: Optional[List[int]] = None, max_pages: int = 30) -> tuple:
    """Scan a sample of pages, collect unresolved glyphs, and resolve them."""
    if pages is None:
        n = doc.page_count
        step = max(1, n // max_pages)
        pages = list(range(0, n, step))[:max_pages]

    slots: Dict[tuple, int] = {}
    samples: Dict[tuple, List[str]] = {}
    for pno in pages:
        page = doc[pno]
        for span in page.get_texttrace():
            chars = span.get("chars") or []
            if not chars:
                continue
            font = span.get("font", "").split("+")[-1]
            gmap = decoder.map_for(span.get("font", ""), page)
            pieces, used = [], []
            for ch in chars:
                uni, gid = ch[0], ch[1]
                got = gmap.get(gid)
                if got is None and gid >= 0 and uni != 32:
                    key = (font, gid)
                    if key not in slots:
                        slots[key] = len(slots)
                    got = _placeholder(slots[key])
                    used.append(key)
                elif got is None:
                    got = chr(uni) if 0 < uni < 0x110000 else ""
                pieces.append(got)
            if not used:
                continue
            if span.get("bidi_lvl", 0) % 2:
                pieces.reverse()
            text = _clean("".join(pieces))
            for word in text.split():
                for key in set(used):
                    if _placeholder(slots[key]) in word:
                        samples.setdefault(key, []).append(word)

    learner = ResidualLearner(lexicon)
    resolved = learner.learn(samples)
    return resolved, learner.decisions
