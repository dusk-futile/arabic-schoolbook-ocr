import pytest

from arabic_schoolbook_ocr.schemas import Direction, Script
from arabic_schoolbook_ocr.text_runs import normalize_unicode, segment_mixed_runs


@pytest.mark.parametrize(
    "text",
    [
        "تحدث عملية Photosynthesis داخل النبات.",
        "افتح Chapter 3 ثم أجب.",
        "درجة الحرارة 25°C.",
        "سرعة الجسم 10 m/s.",
        "النسبة 50% من 200.",
        "H2O هو رمز الماء.",
    ],
)
def test_mixed_runs_preserve_logical_order(text: str) -> None:
    runs = segment_mixed_runs(text)
    assert "".join(run.text for run in runs) == text
    assert normalize_unicode(text) == text


def test_latin_and_arabic_directions_are_explicit() -> None:
    runs = segment_mixed_runs("تحدث Photosynthesis هنا")
    assert any(run.script == Script.ARABIC and run.direction == Direction.RTL for run in runs)
    assert any(run.script == Script.LATIN and run.direction == Direction.LTR for run in runs)
