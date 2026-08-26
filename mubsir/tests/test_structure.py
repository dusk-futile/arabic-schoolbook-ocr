"""Paragraph reconstruction: the decision that ruins an emboss when wrong."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mubsir.model import Line, PageInfo
from mubsir.structure import (build_paragraphs, decide_break, page_geometry,
                              find_gutter, find_furniture)
from mubsir.lines import merge_fragments, find_corridors


def mkline(text, x0, y0, x1, y1, page=1, size=13.0, source="digital"):
    return Line(text=text, bbox=(x0, y0, x1, y1), page=page, size=size, source=source)


def justified_page(n=8, left=80.0, right=515.0, top=90.0, step=21.0):
    """n full-width lines: a paragraph that wraps and never breaks."""
    return [mkline(f"سطر {i}", left, top + i * step, right, top + i * step + 14)
            for i in range(n)]


def test_full_lines_never_break():
    lines = justified_page()
    g = page_geometry(lines, 595, 842)
    assert g.justified
    for a, b in zip(lines, lines[1:]):
        assert not decide_break(a, b, g).is_break


def test_short_line_ends_a_paragraph():
    lines = justified_page(6)
    # RTL: a paragraph's last line starts at the right margin but ends early
    lines.append(mkline("نهاية.", 400.0, 90 + 6 * 21, 515.0, 90 + 6 * 21 + 14))
    lines.append(mkline("جديد", 80.0, 90 + 7 * 21, 515.0, 90 + 7 * 21 + 14))
    g = page_geometry(lines, 595, 842)
    assert decide_break(lines[-2], lines[-1], g).is_break


def test_page_change_always_breaks():
    a = mkline("اخير", 80, 700, 515, 714, page=1)
    b = mkline("اول", 80, 90, 515, 104, page=2)
    g = page_geometry([a, b], 595, 842)
    assert decide_break(a, b, g).is_break


def test_bidi_fragments_merge_into_one_line():
    # One visual line split at a direction change, as extractors emit it.
    frags = [mkline("الكلمة", 300, 100, 515, 114),
             mkline("Psychology", 200, 100, 295, 114),
             mkline("اليونانية", 80, 100, 195, 114)]
    merged = merge_fragments(frags)
    assert len(merged) == 1
    assert merged[0].text.startswith("الكلمة")          # RTL: rightmost first
    assert merged[0].x0 == 80 and merged[0].x1 == 515


def test_two_column_gutter_is_found_and_never_merged_across():
    lines = []
    for i in range(10):
        y = 90 + i * 21
        lines.append(mkline(f"يمين {i}", 310, y, 515, y + 14))   # right column
        lines.append(mkline(f"يسار {i}", 80, y, 285, y + 14))    # left column
    corridors = find_corridors(lines)
    assert corridors, "gutter must be detected"
    a, b = corridors[0]
    assert 280 <= a <= 312 and 285 <= b <= 315
    merged = merge_fragments(lines)
    assert len(merged) == 20, "columns must not be stitched together"


def test_running_head_is_dropped_as_furniture():
    pages = []
    for p in range(1, 5):
        lines = [mkline("سيكولوجية الإبداع", 80, 42, 300, 56, page=p, size=9.5)]
        lines += [mkline(f"نص {p}-{i}", 80, 90 + i * 21, 515, 104 + i * 21, page=p)
                  for i in range(6)]
        pages.append(PageInfo(number=p, width=595, height=842, lines=lines))
    furniture = find_furniture(pages)
    assert len(furniture) == 4, "the running head on every page is furniture"
    paras = build_paragraphs(pages, drop_furniture=True)
    assert not any("سيكولوجية الإبداع" in p.text for p in paras)


def test_soft_wraps_join_with_a_single_space():
    pages = [PageInfo(number=1, width=595, height=842, lines=justified_page(4))]
    paras = build_paragraphs(pages, drop_furniture=False)
    assert len(paras) == 1
    assert "\n" not in paras[0].text
    assert "  " not in paras[0].text
