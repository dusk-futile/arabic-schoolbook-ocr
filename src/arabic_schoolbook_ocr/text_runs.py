from __future__ import annotations

import unicodedata

from .schemas import Direction, Script, TextRun


def normalize_unicode(text: str) -> str:
    """Canonical normalization only; spelling, digits, and presentation remain unchanged."""

    return unicodedata.normalize("NFC", text)


def _classify(character: str) -> tuple[Script, Direction]:
    codepoint = ord(character)
    name = unicodedata.name(character, "")
    if (
        0x0600 <= codepoint <= 0x06FF
        or 0x0750 <= codepoint <= 0x077F
        or 0x08A0 <= codepoint <= 0x08FF
        or 0xFB50 <= codepoint <= 0xFDFF
        or 0xFE70 <= codepoint <= 0xFEFF
    ):
        return Script.ARABIC, Direction.RTL
    if "LATIN" in name:
        return Script.LATIN, Direction.LTR
    if character.isdigit():
        return Script.DIGIT, Direction.LTR
    return Script.NEUTRAL, Direction.NEUTRAL


def segment_mixed_runs(text: str) -> list[TextRun]:
    """Segment logical-order Unicode into formatting runs; never reverse characters."""

    if not text:
        return []
    raw: list[tuple[str, Script, Direction]] = []
    for character in text:
        script, direction = _classify(character)
        if raw and script == Script.NEUTRAL:
            previous = raw[-1]
            raw[-1] = (previous[0] + character, previous[1], previous[2])
        elif raw and raw[-1][1:] == (script, direction):
            previous = raw[-1]
            raw[-1] = (previous[0] + character, script, direction)
        else:
            raw.append((character, script, direction))
    if raw and raw[0][1] == Script.NEUTRAL and len(raw) > 1:
        first, second = raw[0], raw[1]
        raw[1] = (first[0] + second[0], second[1], second[2])
        raw.pop(0)
    return [
        TextRun(text=part, script=script, direction=direction) for part, script, direction in raw
    ]
