"""Repair of bidi-fragmented lines.

A PDF text extractor emits one "line" per directional run, so a single visual
line of Arabic containing a Latin word or a quotation mark arrives as two,
three or four fragments. Left alone this destroys every geometric signal the
structure engine depends on - a full justified line looks like four short ones
and every one of them reads as a paragraph end.

Fragments are regrouped by shared baseline and re-ordered right-to-left. The
horizontal-gap guard is what keeps a two-column page from having its columns
stitched together into one line.
"""
from __future__ import annotations

from typing import List

from .model import Line

MERGE_GAP_EM = 1.35      # max horizontal gap, in em, still counted as one line
ROW_OVERLAP = 0.55       # vertical overlap needed to share a baseline
SPACE_GAP_EM = 0.12      # gap above which a space is inserted when joining


def _v_overlap(a: Line, b: Line) -> float:
    top, bot = max(a.y0, b.y0), min(a.y1, b.y1)
    inter = max(0.0, bot - top)
    smaller = min(a.height, b.height) or 1.0
    return inter / smaller


def group_rows(lines: List[Line]) -> List[List[Line]]:
    rows: List[List[Line]] = []
    for line in sorted(lines, key=lambda l: (l.y0, -l.x1)):
        for row in rows:
            if _v_overlap(line, row[-1]) >= ROW_OVERLAP:
                row.append(line)
                break
        else:
            rows.append([line])
    return rows


def find_corridors(lines: List[Line], min_frac: float = 0.035) -> List[tuple]:
    """Vertical whitespace corridors that no fragment may be merged across.

    A two-column gutter can be narrower than the merge gap: with 13 pt type the
    gap threshold is about 17 pt and a typical gutter is 18 pt, so the right
    column's line and the left column's line on the same row get stitched into
    one. That silently destroys ~10% of the lines on a two-column page. Finding
    the corridors first makes the merge respect columns by construction rather
    than by a threshold that happens to fit.
    """
    if len(lines) < 8:
        return []
    lo = int(min(l.x0 for l in lines))
    hi = int(max(l.x1 for l in lines)) + 1
    span = hi - lo
    if span < 40:
        return []
    cov = [0] * (span + 1)
    for l in lines:
        a = max(0, int(l.x0) - lo)
        b = min(span, int(round(l.x1)) - lo)
        for i in range(a, b + 1):
            cov[i] += 1
    limit = max(1, int(len(lines) * 0.06))
    corridors, start = [], None
    for i, c in enumerate(cov):
        if c <= limit:
            if start is None:
                start = i
        else:
            if start is not None and (i - start) >= max(6, span * min_frac):
                corridors.append((start + lo, i + lo))
            start = None
    # a corridor touching either edge is a margin, not a gutter
    return [(a, b) for a, b in corridors if a > lo + span * 0.12 and b < hi - span * 0.12]


def merge_fragments(lines: List[Line], rtl: bool = True) -> List[Line]:
    if not lines:
        return []
    corridors = find_corridors(lines)
    out: List[Line] = []
    for row in group_rows(lines):
        # RTL reading order along the row: rightmost fragment first
        row.sort(key=lambda l: -l.x1 if rtl else l.x0)
        row = drop_overdrawn(row)
        chunk: List[Line] = [row[0]]
        for frag in row[1:]:
            prev = chunk[-1]
            gap = (prev.x0 - frag.x1) if rtl else (frag.x0 - prev.x1)
            em = max(prev.size, frag.size, 1.0)
            lo_x = min(prev.x0, frag.x1) if rtl else min(prev.x1, frag.x0)
            hi_x = max(prev.x0, frag.x1) if rtl else max(prev.x1, frag.x0)
            crosses = any(lo_x <= (a + b) / 2 <= hi_x for a, b in corridors)
            if gap <= em * MERGE_GAP_EM and not crosses:
                chunk.append(frag)
            else:
                out.append(_fuse(chunk, rtl))
                chunk = [frag]
        out.append(_fuse(chunk, rtl))
    out.sort(key=lambda l: (l.y0, -l.x1 if rtl else l.x0))
    return out


def drop_overdrawn(row: List[Line]) -> List[Line]:
    """Remove text drawn twice in the same place.

    Title pages often stack an identical text run on itself to fake a bold or
    shadowed effect. Both copies are real draw operations, so the extractor
    reports both and the merge would concatenate them - turning "\u0625\u0639\u062f\u0627\u062f" into
    "\u0625\u0639\u062f\u0627\u062f\u0625\u0639\u062f\u0627\u062f". A duplicate is only dropped when the text matches
    and the boxes genuinely sit on top of each other.
    """
    kept: List[Line] = []
    for line in row:
        text = line.text.strip()
        dup = False
        for k in kept:
            if k.text.strip() != text or not text:
                continue
            lo, hi = max(line.x0, k.x0), min(line.x1, k.x1)
            overlap = max(0.0, hi - lo)
            narrower = min(line.width, k.width) or 1.0
            if overlap / narrower > 0.5:
                dup = True
                break
        if not dup:
            kept.append(line)
    return kept


def _fuse(chunk: List[Line], rtl: bool) -> Line:
    if len(chunk) == 1:
        return chunk[0]
    parts: List[str] = []
    for i, frag in enumerate(chunk):
        t = frag.text
        if i:
            prev = chunk[i - 1]
            gap = (prev.x0 - frag.x1) if rtl else (frag.x0 - prev.x1)
            em = max(prev.size, frag.size, 1.0)
            need_space = gap > em * SPACE_GAP_EM
            if need_space and parts and not parts[-1].endswith(" ") and not t.startswith(" "):
                parts.append(" ")
        parts.append(t)
    text = "".join(parts)
    x0 = min(f.x0 for f in chunk)
    y0 = min(f.y0 for f in chunk)
    x1 = max(f.x1 for f in chunk)
    y1 = max(f.y1 for f in chunk)
    widest = max(chunk, key=lambda f: len(f.text.strip()))
    return Line(
        text=text, bbox=(x0, y0, x1, y1), page=chunk[0].page,
        size=widest.size, conf=min(f.conf for f in chunk),
        source=chunk[0].source,
        bold=sum(len(f.text) for f in chunk if f.bold) > sum(len(f.text) for f in chunk) / 2,
        font=widest.font,
    )
