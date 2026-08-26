"""Reading order on multi-column right-to-left pages.

The property that matters most is not that the order is clever but that it is
*total*: the earlier approach cut the page into columns and read each in turn,
which silently dropped any line that straddled a split. A topological sort over
the lines cannot lose one, and the first test here pins that down.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from mubsir.model import Line
from mubsir.reading_order import order_lines

W = 595.0


def L(text, x0, y0, x1, y1):
    return Line(text=text, bbox=(x0, y0, x1, y1), page=1, size=13.0)


def two_column_page():
    """Running head, two columns, a cross-column subheading, a page number."""
    lines = [L("HEAD", 80, 40, 300, 54)]
    lines += [L(f"R{i+1}", 310, 90 + i * 20, 515, 104 + i * 20) for i in range(4)]
    lines += [L(f"L{i+1}", 80, 90 + i * 20, 285, 104 + i * 20) for i in range(4)]
    lines += [L("SUBHEAD", 80, 190, 515, 204)]
    lines += [L(f"r{i+1}", 310, 220 + i * 20, 515, 234 + i * 20) for i in range(3)]
    lines += [L(f"l{i+1}", 80, 220 + i * 20, 285, 234 + i * 20) for i in range(3)]
    lines += [L("PAGENO", 290, 790, 305, 804)]
    return lines


def test_never_loses_or_duplicates_a_line():
    lines = two_column_page()
    out = order_lines(lines, W, rtl=True)
    assert len(out) == len(lines)
    assert sorted(l.text for l in out) == sorted(l.text for l in lines)


def test_right_column_is_read_before_left():
    out = [l.text for l in order_lines(two_column_page(), W, rtl=True)]
    assert out.index("R1") < out.index("L1")
    assert out.index("R4") < out.index("L1")


def test_cross_column_heading_separates_the_bands():
    out = [l.text for l in order_lines(two_column_page(), W, rtl=True)]
    assert out.index("L4") < out.index("SUBHEAD") < out.index("r1")


def test_full_expected_order():
    out = [l.text for l in order_lines(two_column_page(), W, rtl=True)]
    assert out == ["HEAD", "R1", "R2", "R3", "R4", "L1", "L2", "L3", "L4",
                   "SUBHEAD", "r1", "r2", "r3", "l1", "l2", "l3", "PAGENO"]


def test_abutting_columns_do_not_create_a_cycle():
    # When boxes touch exactly, "not left of" is true in both directions, which
    # makes a 2-cycle and scrambles a naive topological sort.
    lines = [L("R1", 300, 90, 595, 104), L("R2", 300, 110, 595, 124),
             L("L1", 0, 90, 300, 104), L("L2", 0, 110, 300, 124)]
    out = [l.text for l in order_lines(lines, W, rtl=True)]
    assert out == ["R1", "R2", "L1", "L2"]


def test_unequal_column_lengths():
    lines = [L("R1", 310, 90, 515, 104), L("R2", 310, 110, 515, 124),
             L("R3", 310, 130, 515, 144),
             L("L1", 80, 90, 285, 104), L("L2", 80, 110, 285, 124)]
    out = [l.text for l in order_lines(lines, W, rtl=True)]
    assert out == ["R1", "R2", "R3", "L1", "L2"]


def test_single_column_is_simply_top_to_bottom():
    lines = [L(f"n{i}", 80, 90 + i * 20, 515, 104 + i * 20) for i in range(6)]
    out = [l.text for l in order_lines(lines, W, rtl=True)]
    assert out == [f"n{i}" for i in range(6)]


def test_left_to_right_mode_reverses_the_column_preference():
    lines = [L("A", 310, 90, 515, 104), L("B", 80, 90, 285, 104)]
    assert [l.text for l in order_lines(lines, W, rtl=True)] == ["A", "B"]
    assert [l.text for l in order_lines(lines, W, rtl=False)] == ["B", "A"]
