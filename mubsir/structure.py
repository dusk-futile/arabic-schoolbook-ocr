"""Structure reconstruction - the part that decides whether a line break is a
soft wrap or a real paragraph break.

This is the emboss-killer, so the logic is deterministic, weighted, and every
decision carries the reasons that produced it. Nothing here uses a model.

Direction convention throughout: Arabic is RTL, so a line *starts* at its x1
(right edge) and *ends* at its x0 (left edge).

  - a line that ends short  -> x0 far from the left margin -> paragraph end
  - a line that is indented -> x1 short of the right margin -> paragraph start
"""
from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .arabic import TERMINAL_PUNCT, canonical, search_form
from .model import (BODY, CAPTION, FOOTNOTE, HEADING, LIST_ITEM, SUBHEADING,
                    TITLE, Line, PageInfo, Para)

# --------------------------------------------------------------- tunables
FULL_LINE = 0.94          # fill ratio at/above which a line reached the margin
SHORT_END = 0.12          # left-gap (as share of column) meaning "ended early"
INDENT_MIN = 0.015        # right-gap meaning "indented"
INDENT_MAX = 0.28         # beyond this it is centring, not indentation
GAP_FACTOR = 1.42         # vertical gap multiple that signals a break
SIZE_DELTA = 0.75         # font-size points that signal a different role
BREAK_THRESHOLD = 0.50
JUSTIFIED_AT = 0.55       # share of full lines meaning the text is justified

LIST_RE = re.compile(
    r"^\s*(?:"
    r"[\(\[]?\s*[0-9٠-٩۰-۹]{1,3}\s*[\)\]\.\-–—:]"
    r"|[\(\[]?\s*[أ-يabcdefghij]\s*[\)\]\.\-–—]"
    r"|[-–—•*·◦▪]\s+"
    r"|(?:أولا|ثانيا|ثالثا|رابعا|خامسا|سادسا|سابعا|ثامنا|تاسعا|عاشرا)ً?\s*[:\-–—]?"
    r")\s*"
)
NUMERIC_ONLY = re.compile(r"^[\s\-–—\[\(]*[0-9٠-٩۰-۹]{1,4}[\s\-–—\]\)\.]*$")
FOOTNOTE_MARK = re.compile(r"^\s*[\(\[]?\s*[0-9٠-٩]{1,3}\s*[\)\]]?\s*[-–—]?\s*")


@dataclass
class Geometry:
    left: float
    right: float
    width: float
    body_size: float
    gap: float
    justified: bool
    fill_mean: float
    page_w: float
    page_h: float


# --------------------------------------------------------------- features
FEATURE_NAMES = [
    "left_gap",        # RTL: how early the previous line ended (share of column)
    "right_gap",       # RTL: how far this line is indented from the right margin
    "prev_fill",       # how much of the column the previous line used
    "gap_ratio",       # vertical gap / modal line gap
    "terminal_punct",  # previous line ends a sentence
    "cont_punct",      # previous line ends mid-clause
    "list_marker",     # this line opens a list item
    "centred",         # this line is centred and short
    "justified",       # the block is justified, so short lines are meaningful
    "size_ratio",      # relative type size change
    "bias",
]


def break_features(prev: Line, cur: Line, g: "Geometry") -> List[float]:
    """The evidence a paragraph-break decision rests on, as plain numbers.

    Shared by the hand-weighted scorer and the learned one, so both see exactly
    the same view of the page and can be compared honestly.
    """
    width = g.width or 1.0
    left_gap = (prev.x0 - g.left) / width
    right_gap = (g.right - cur.x1) / width
    vgap = (cur.y0 - prev.y0) / g.gap if g.gap > 0 else 1.0
    stripped = prev.text.rstrip()
    last = stripped[-1] if stripped else ""
    center = (g.left + g.right) / 2
    lo, hi = min(prev.size, cur.size), max(prev.size, cur.size)
    return [
        max(-0.5, min(1.5, left_gap)),
        max(-0.5, min(1.5, right_gap)),
        _fill(prev, g.left, g.right),
        max(0.0, min(6.0, vgap)),
        1.0 if last in TERMINAL_PUNCT else 0.0,
        1.0 if last in "\u060c\u061b,-\u2013\u2014" else 0.0,
        1.0 if LIST_RE.match(cur.text) else 0.0,
        1.0 if (abs(cur.cx - center) < width * 0.06 and cur.width < width * 0.72) else 0.0,
        1.0 if g.justified else 0.0,
        max(0.5, min(2.5, (hi / lo) if lo > 0.1 else 1.0)),
        1.0,
    ]


def _size_differs(a: float, b: float, g: "Geometry", noisy: bool = False) -> bool:
    """Do two lines use materially different type sizes?

    The two front-ends mean different things by "size", so they are compared
    differently. A digital line reports the real font size and can be trusted
    to a fraction of a point. An OCR line reports its detected box height,
    which swings by 10-20% depending on whether the line happens to contain
    ascenders or descenders - so an absolute threshold there turns ordinary
    jitter into a paragraph break on every single line.
    """
    lo, hi = min(a, b), max(a, b)
    if lo <= 0.1:
        return False
    if not noisy:
        return (hi - lo) > SIZE_DELTA
    return (hi / lo) > 1.28 and (hi - lo) > max(SIZE_DELTA, g.body_size * 0.16)


def snap_margins(lines: List[Line], g: "Geometry", tol: float = 0.022) -> int:
    """Pull near-margin OCR line edges onto the margin itself.

    A detector's box hugs the ink, so the same physical margin lands a few
    points differently on every line depending on the first and last glyph -
    an 'ا' reaches the margin, a 'و' does not. That noise is indistinguishable
    from a real short line or a real indent, which is exactly the distinction
    the paragraph logic rests on. Snapping only moves edges that are already
    within ~2% of the margin, so a genuinely short or indented line is left
    alone.
    """
    if not lines:
        return 0
    slack = g.width * tol
    moved = 0
    for l in lines:
        x0, y0, x1, y1 = l.bbox
        nx0, nx1 = x0, x1
        if abs(x1 - g.right) <= slack:
            nx1 = g.right
        if abs(x0 - g.left) <= slack:
            nx0 = g.left
        if (nx0, nx1) != (x0, x1):
            l.bbox = (nx0, y0, nx1, y1)
            moved += 1
    return moved


def _fill(line: Line, g_left: float, g_right: float) -> float:
    span = g_right - g_left
    return min(line.width / span, 1.0) if span > 0 else 0.0


def _modal(values: Sequence[float], bucket: float = 0.5) -> float:
    if not values:
        return 0.0
    counts = Counter(round(v / bucket) * bucket for v in values)
    return counts.most_common(1)[0][0]


def page_geometry(lines: List[Line], page_w: float, page_h: float) -> Optional[Geometry]:
    """Robust column geometry from the body lines only.

    Headings and page furniture are excluded by restricting to the modal font
    size, otherwise a centred title drags the margins inward.
    """
    if not lines:
        return None
    sizes = [l.size for l in lines]
    body_size = _modal(sizes, 0.5) or statistics.median(sizes)
    # Selecting the body lines needs the same source-awareness as the break
    # rule: an absolute tolerance discards most OCR lines (whose "size" is a
    # jittery box height), leaving a handful whose vertical spacing skips
    # intervening lines and yields a nonsense modal line gap.
    noisy = any(l.source == "ocr" for l in lines)
    tol = max(SIZE_DELTA, body_size * 0.22) if noisy else SIZE_DELTA
    body = [l for l in lines if abs(l.size - body_size) <= tol] or lines

    xs1 = sorted(l.x1 for l in body)
    xs0 = sorted(l.x0 for l in body)
    right = xs1[int(len(xs1) * 0.90)] if len(xs1) > 4 else max(xs1)
    left = xs0[int(len(xs0) * 0.10)] if len(xs0) > 4 else min(xs0)
    width = right - left
    if width <= 1:
        return None

    ys = sorted(body, key=lambda l: l.y0)
    gaps = [b.y0 - a.y0 for a, b in zip(ys, ys[1:]) if 0 < b.y0 - a.y0 < page_h * 0.25]
    gap = _modal(gaps, 0.5) if gaps else body_size * 1.5

    fills = [_fill(l, left, right) for l in body]
    full_share = sum(1 for f in fills if f >= FULL_LINE) / len(fills)
    return Geometry(
        left=left, right=right, width=width, body_size=body_size,
        gap=gap or body_size * 1.5, justified=full_share >= JUSTIFIED_AT,
        fill_mean=statistics.fmean(fills), page_w=page_w, page_h=page_h,
    )


# --------------------------------------------------------------- furniture
def find_furniture(pages: List[PageInfo], min_share: float = 0.34) -> set:
    """Running heads, running feet and page numbers.

    Detected by repetition across pages at a stable vertical band, which is
    what actually distinguishes furniture from a short body line. In Braille
    these are noise, so they are dropped rather than emitted.
    """
    if len(pages) < 3:
        return set()

    # (relative y, normalised text, line id, page)
    cands: List[tuple] = []
    for p in pages:
        if not p.lines or p.height <= 0:
            continue
        ordered = sorted(p.lines, key=lambda l: l.y0)
        gaps = [b.y0 - a.y0 for a, b in zip(ordered, ordered[1:]) if b.y0 > a.y0]
        modal_gap = _modal(gaps, 0.5) if gaps else 0.0
        for idx, l in enumerate(ordered):
            rel = l.y0 / p.height
            if not (rel < 0.13 or rel > 0.87):
                continue
            # Being near the top is not enough. The first body line often sits
            # inside the top 13% too, and once digits are masked "نص 1-0" and
            # "نص 2-0" look identical across pages - so body text would be
            # deleted as a running head. Real furniture is visually detached:
            # it sits alone, separated from the text block by more than a
            # normal line gap.
            if modal_gap > 0:
                below = ordered[idx + 1].y0 - l.y0 if idx + 1 < len(ordered) else None
                above = l.y0 - ordered[idx - 1].y0 if idx else None
                detached = ((below is not None and below > modal_gap * 1.6)
                            if rel < 0.13 else
                            (above is not None and above > modal_gap * 1.6))
                if not detached:
                    continue
            key_txt = re.sub(r"[0-9٠-٩]+", "#", search_form(l.text)) or "#"
            cands.append((rel, key_txt, id(l), p.number))

    n = len(pages)
    marked = set()
    used = [False] * len(cands)
    for i, (rel_i, txt_i, _, _) in enumerate(cands):
        if used[i]:
            continue
        group = [i]
        pages_seen = {cands[i][3]}
        for j in range(i + 1, len(cands)):
            if used[j]:
                continue
            rel_j, txt_j, _, page_j = cands[j]
            # Position tolerance rather than fixed bands: a fixed band puts the
            # running head and the first body line in the same bucket, and also
            # splits a head that drifts a couple of points between scans.
            if abs(rel_j - rel_i) > 0.025:
                continue
            # OCR never renders a running head character-identically twice.
            if SequenceMatcher(None, txt_i, txt_j).ratio() < 0.72:
                continue
            group.append(j)
            pages_seen.add(page_j)
        if len(pages_seen) / n >= min_share and len(pages_seen) >= 3:
            for k in group:
                used[k] = True
                marked.add(cands[k][2])
    # standalone page numbers are furniture even without repetition
    for p in pages:
        if p.height <= 0:
            continue
        for l in p.lines:
            rel = l.y0 / p.height
            if (rel < 0.13 or rel > 0.87) and NUMERIC_ONLY.match(l.text.strip()):
                marked.add(id(l))
    return marked


# --------------------------------------------------------------- columns
def find_gutter(lines: List[Line], g: Geometry) -> Optional[tuple]:
    """Locate a vertical whitespace corridor by horizontal coverage projection.

    Clustering line centres does not work: a short final line sits far from its
    column's centre, so the centre gap lands inside a column rather than in the
    gutter. Projecting actual line extents finds the corridor where no text
    exists, which is what a gutter physically is.

    Lines wider than 60% of the text block are excluded - a heading spanning
    both columns would otherwise paint over the corridor and hide it.
    """
    narrow = [l for l in lines if l.width < g.width * 0.60]
    if len(narrow) < 6:
        return None
    lo, hi = int(g.left), int(g.right) + 1
    cov = [0] * (hi - lo + 1)
    for l in narrow:
        a = max(lo, int(l.x0)) - lo
        b = min(hi, int(round(l.x1))) - lo
        for i in range(a, b + 1):
            cov[i] += 1
    # A gutter is a corridor almost no line crosses, not one that literally
    # none does. Demanding exact zero makes detection hostage to a single
    # over-wide detector box: on OCR pages that one stray box hid the gutter
    # entirely and the two columns were read interleaved.
    limit = max(1, int(len(narrow) * 0.08))
    best = None
    run_start = None
    for i, c in enumerate(cov):
        if c <= limit:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None:
                if best is None or (i - run_start) > (best[1] - best[0]):
                    best = (run_start, i)
                run_start = None
    if run_start is not None and (len(cov) - run_start) > (0 if best is None else best[1] - best[0]):
        best = (run_start, len(cov))
    if best is None:
        return None
    a, b = best[0] + lo, best[1] + lo
    mid = (a + b) / 2
    # a real gutter is reasonably wide and sits away from the page edges
    if (b - a) < max(8.0, g.width * 0.025):
        return None
    if not (g.left + g.width * 0.22 < mid < g.right - g.width * 0.22):
        return None
    return (a, b)


def assign_columns(lines: List[Line], g: Geometry) -> int:
    """Assign RTL column indices (0 = rightmost). Spanning lines get -1."""
    for l in lines:
        l.column = 0
    if len(lines) < 8:
        return 1
    gut = find_gutter(lines, g)
    if gut is None:
        return 1
    a, b = gut
    right = [l for l in lines if l.x0 >= b - 1]
    left = [l for l in lines if l.x1 <= a + 1]
    span = [l for l in lines if l not in right and l not in left]
    if min(len(right), len(left)) < max(3, len(lines) * 0.15):
        return 1
    if len(span) > len(lines) * 0.30:
        return 1
    for l in right:
        l.column = 0
    for l in left:
        l.column = 1
    for l in span:
        l.column = -1
    return 2


def order_page_lines(lines: List[Line], g: Geometry) -> List[Line]:
    """Reading order for one page.

    Columns are still *assigned*, because the break logic needs per-column
    margins, but they no longer determine the order. Ordering is a topological
    sort over the lines themselves (see mubsir/reading_order.py): partitioning
    a page into columns and reading each in turn drops any line that straddles
    a split or falls outside a detected column, which was losing about 9% of
    the lines on two-column scans. A sort over the lines cannot lose one.
    """
    assign_columns(lines, g)
    from .reading_order import order_lines
    return order_lines(lines, g.page_w or 595.0, rtl=True)


# --------------------------------------------------------------- break logic
@dataclass
class Decision:
    is_break: bool
    score: float
    reasons: List[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        return min(1.0, abs(self.score - BREAK_THRESHOLD) * 2 + 0.5)


def decide_break(prev: Line, cur: Line, g: Geometry) -> Decision:
    reasons: List[str] = []

    if cur.page != prev.page:
        return Decision(True, 1.0, ["page-change"])
    if cur.column != prev.column:
        return Decision(True, 1.0, ["column-change"])

    noisy = prev.source == "ocr" or cur.source == "ocr"
    if _size_differs(prev.size, cur.size, g, noisy=noisy):
        return Decision(True, 1.0, [f"size-change {prev.size}->{cur.size}"])
    if cur.bold != prev.bold:
        return Decision(True, 0.95, ["weight-change"])

    score = 0.0
    left_gap = (prev.x0 - g.left) / g.width          # RTL: how early prev ended
    right_gap = (g.right - cur.x1) / g.width          # RTL: how far cur is indented
    vgap = cur.y0 - prev.y0

    prev_fill = _fill(prev, g.left, g.right)
    if g.justified:
        # Justified text is the easy, reliable case: only the final line of a
        # paragraph is allowed to end short.
        if left_gap > SHORT_END:
            score += 0.72
            reasons.append(f"prev-ends-short({left_gap:.2f})")
        elif prev_fill >= FULL_LINE:
            score -= 0.45
            reasons.append("prev-line-full")
    else:
        # Ragged text: short lines are normal mid-paragraph, so this signal is
        # weak on its own and the others have to carry the decision.
        if left_gap > SHORT_END * 2.0:
            score += 0.34
            reasons.append(f"prev-ends-very-short({left_gap:.2f})")

    if INDENT_MIN < right_gap < INDENT_MAX:
        score += 0.42
        reasons.append(f"indent({right_gap:.2f})")

    if g.gap > 0 and vgap > g.gap * GAP_FACTOR:
        score += 0.40
        reasons.append(f"gap({vgap / g.gap:.2f}x)")
    elif g.gap > 0 and vgap < g.gap * 1.06:
        score -= 0.12

    stripped = prev.text.rstrip()
    if stripped and stripped[-1] in TERMINAL_PUNCT:
        score += 0.22
        reasons.append("terminal-punct")
    elif stripped and stripped[-1] in "،؛,-–—":
        score -= 0.28
        reasons.append("continuation-punct")

    if LIST_RE.match(cur.text):
        score += 0.55
        reasons.append("list-marker")

    # A centred short line is a heading, not a continuation.
    center = (g.left + g.right) / 2
    if abs(cur.cx - center) < g.width * 0.06 and cur.width < g.width * 0.72:
        score += 0.35
        reasons.append("centred")

    return Decision(score >= BREAK_THRESHOLD, score, reasons)


# --------------------------------------------------------------- classify
def classify(lines: List[Line], g: Geometry, page_h: float) -> str:
    first = lines[0]
    text = first.text.strip()
    noisy = any(l.source == "ocr" for l in lines)
    size_delta = statistics.fmean([l.size for l in lines]) - g.body_size
    size_floor = max(SIZE_DELTA, g.body_size * 0.16) if noisy else SIZE_DELTA
    center = (g.left + g.right) / 2
    centred = all(abs(l.cx - center) < g.width * 0.08 for l in lines)
    short = all(l.width < g.width * 0.82 for l in lines)

    if size_delta > g.body_size * 0.42:
        return TITLE
    if size_delta > size_floor:
        return HEADING if size_delta > g.body_size * 0.22 else SUBHEADING
    if LIST_RE.match(text):
        return LIST_ITEM
    if size_delta < -size_floor and first.y0 > page_h * 0.68:
        return FOOTNOTE
    if (centred or first.bold) and short and len(lines) <= 3 and text and text[-1] not in ".؟!":
        return SUBHEADING
    return BODY


def _join(lines: List[Line]) -> str:
    """Arabic does not hyphenate across lines, so a plain space is correct.
    Latin fragments inside the text may still hyphenate, so handle that."""
    parts: List[str] = []
    for i, l in enumerate(lines):
        t = l.text.strip()
        if i and parts and parts[-1].endswith("-") and re.search(r"[A-Za-z]-$", parts[-1]):
            parts[-1] = parts[-1][:-1] + t
            continue
        parts.append(t)
    return " ".join(p for p in parts if p)


def build_paragraphs(pages: List[PageInfo], drop_furniture: bool = True,
                     use_model: bool = True,
                     model_threshold: float = 0.80) -> List[Para]:
    furniture = find_furniture(pages) if drop_furniture else set()

    ordered: List[Line] = []
    geoms: Dict[tuple, Geometry] = {}          # (page, column) -> Geometry
    for p in pages:
        lines = [l for l in p.lines if id(l) not in furniture and l.text.strip()]
        if not lines:
            continue
        page_g = page_geometry(lines, p.width, p.height)
        if page_g is None:
            continue
        lines = order_page_lines(lines, page_g)
        cols = sorted({l.column for l in lines})
        ncols = len([c for c in cols if c >= 0])
        if ncols > 1:
            p.notes.append(f"{ncols} columns")

        # Geometry is per column, never per page. On a two-column page the
        # page-wide margins make every line look half-width, so every line
        # reads as a paragraph end and the page shatters.
        for col in cols:
            col_lines = [l for l in lines if l.column == col]
            g = page_geometry(col_lines, p.width, p.height) if len(col_lines) >= 3 else page_g
            g = g or page_g
            if any(l.source == "ocr" for l in col_lines):
                n_snapped = snap_margins(col_lines, g)
                g = page_geometry(col_lines, p.width, p.height) or g
                if n_snapped:
                    p.notes.append(f"snapped {n_snapped} line edges to margins")
            geoms[(p.number, col)] = g
        ordered.extend(lines)

    if not ordered:
        return []

    # Pass 1: score every boundary deterministically, keeping the reasons.
    decisions: List[Decision] = []
    for prev, line in zip(ordered, ordered[1:]):
        g = (geoms.get((line.page, line.column))
             or geoms.get((prev.page, prev.column))
             or next((v for k, v in geoms.items() if k[0] == line.page), None))
        decisions.append(decide_break(prev, line, g) if g is not None
                         else Decision(False, 0.0, ["no-geometry"]))

    # Pass 2: the learned classifier breaks ties. The rules keep every boundary
    # they are confident about; this is consulted only where they are not,
    # which is a few percent of boundaries on a normal page.
    if use_model:
        from .boundary_model import get_model
        model = get_model()
        if model.available:
            for i, (prev, line) in enumerate(zip(ordered, ordered[1:])):
                if decisions[i].confidence >= model_threshold:
                    continue
                if prev.page != line.page or prev.column != line.column:
                    continue      # a page or column change is never in doubt
                g = (geoms.get((line.page, line.column))
                     or next((v for k, v in geoms.items() if k[0] == line.page), None))
                if g is None:
                    continue
                feats = break_features(prev, line, g)
                p = model.probability(feats)
                if p is None:
                    continue
                decisions[i] = Decision(
                    p >= model.threshold,
                    min(1.0, abs(p - model.threshold) * 2 + 0.5),
                    decisions[i].reasons + [f"model({p:.2f}:{model.explain(feats)})"],
                )

    paras: List[Para] = []
    cur: List[Line] = [ordered[0]]
    cur_conf: List[float] = []
    cur_reasons: List[str] = []
    for i, line in enumerate(ordered[1:]):
        d = decisions[i]
        if d.is_break:
            paras.append(_make_para(cur, geoms, cur_conf, cur_reasons))
            cur, cur_conf, cur_reasons = [line], [], []
        else:
            cur.append(line)
            cur_conf.append(d.confidence)
            cur_reasons.extend(d.reasons)
    paras.append(_make_para(cur, geoms, cur_conf, cur_reasons))
    return [p for p in paras if p.text.strip()]


def _make_para(lines, geoms, confs, reasons) -> Para:
    first = lines[0]
    g = (geoms.get((first.page, first.column))
         or next((v for k, v in geoms.items() if k[0] == first.page), None))
    page_h = g.page_h if g else 842.0
    kind = classify(lines, g, page_h) if g else BODY
    text = canonical(_join(lines))
    ocr_conf = [l.conf for l in lines if l.source == "ocr"]
    conf = min(
        [min(confs) if confs else 1.0] + ([min(ocr_conf)] if ocr_conf else [])
    )
    flags: List[str] = []
    if confs and min(confs) < 0.72:
        flags.append("uncertain-join")
    if ocr_conf and min(ocr_conf) < 0.80:
        flags.append("low-ocr-confidence")
    return Para(kind=kind, text=text, lines=list(lines), conf=conf, flags=flags)
