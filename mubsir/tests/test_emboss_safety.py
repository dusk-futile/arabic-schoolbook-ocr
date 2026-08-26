"""The space-vs-return guarantee, enforced rather than assumed.

A Braille embosser treats a space and a paragraph mark as different
instructions: a space is a cell, a paragraph mark ends a block. So a stray
newline inside a paragraph, a tab, a doubled space or an invisible bidi
control is a correctness fault, not a cosmetic one. These are the tests that
hold that line.

Characters are written as escapes on purpose - the whole point is the ones you
cannot see in an editor.
"""
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mubsir.docx_out import build_docx, build_plain_text, emboss_safe
from mubsir.model import BODY, HEADING, Para

# Whitespace that is not U+0020 but renders like it.
EXOTIC_SPACES = [
    " ",  # no-break space
    " ",  # figure space
    " ",  # narrow no-break space
    " ",  # thin space
    " ",  # hair space
    " ",  # line separator
    " ",  # paragraph separator
    "",  # vertical tab
    "",  # form feed
]

# Invisible direction controls. In Braille these become stray cells or, worse,
# silently reorder the line.
BIDI_CONTROLS = [
    "‎", "‏", "‪", "‫", "‬",
    "‭", "‮", "⁦", "⁧", "⁨",
    "⁩", "؜",
]

ZERO_WIDTH = ["​", "‌", "‍", "﻿", "­", "⁠"]


def test_newline_inside_paragraph_becomes_one_space():
    assert emboss_safe("سطر\nثان") == "سطر ثان"
    assert emboss_safe("سطر\r\nثان") == "سطر ثان"


def test_double_spaces_collapse():
    assert emboss_safe("كلمة    أخرى") == "كلمة أخرى"


def test_tabs_become_a_single_space():
    assert emboss_safe("كلمة\tأخرى") == "كلمة أخرى"


def test_exotic_spaces_become_a_plain_space():
    for ch in EXOTIC_SPACES:
        assert emboss_safe("كلمة" + ch + "أخرى") == "كلمة أخرى", repr(ch)


def test_bidi_controls_removed_entirely():
    for ch in BIDI_CONTROLS:
        out = emboss_safe("كلمة" + ch + "أخرى")
        assert ch not in out, repr(ch)


def test_zero_width_characters_removed():
    for ch in ZERO_WIDTH:
        assert ch not in emboss_safe("كلمة" + ch + "أخرى"), repr(ch)


def test_leading_and_trailing_space_stripped():
    assert emboss_safe("   كلمة   ") == "كلمة"


def test_written_docx_has_no_hard_line_breaks(tmp_path):
    paras = [
        Para(kind=HEADING, text="عنوان\nمكسور"),
        Para(kind=BODY, text="نص  فيه\tمسافات\nزائدة"),
        Para(kind=BODY, text="‏نص اتجاه‬"),
    ]
    out = str(tmp_path / "t.docx")
    build_docx(paras, out)
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    # No manual line breaks anywhere: Word must do the wrapping, not us.
    assert not re.search(r"<w:br(?![a-zA-Z])", xml)
    assert "<w:tab/>" not in xml

    import docx
    for p in docx.Document(out).paragraphs:
        assert "\n" not in p.text and "\r" not in p.text
        assert "  " not in p.text
        assert p.text == p.text.strip()
        for ch in BIDI_CONTROLS + ZERO_WIDTH:
            assert ch not in p.text, repr(ch)


def test_plain_text_uses_a_blank_line_only_between_paragraphs(tmp_path):
    paras = [Para(kind=BODY, text="أولى\nسطر"), Para(kind=BODY, text="ثانية")]
    out = str(tmp_path / "t.txt")
    build_plain_text(paras, out)
    body = open(out, encoding="utf-8").read()
    assert body.strip() == "أولى سطر\n\nثانية"
    assert "\n\n\n" not in body
