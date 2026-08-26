"""Shared intermediate representation.

Both front-ends (born-digital PDF text layer, OCR) produce ``Line`` objects.
Everything downstream - structure reconstruction, normalisation, output -
consumes only ``Line``. That is the whole point: one structure engine, two
front-ends, so paragraph logic is tested once and behaves identically no
matter where the characters came from.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple, Optional


@dataclass
class Line:
    text: str
    bbox: Tuple[float, float, float, float]   # x0, y0, x1, y1 in PDF points
    page: int
    size: float = 12.0
    conf: float = 1.0
    source: str = "digital"                    # digital | ocr
    bold: bool = False
    font: str = ""
    column: int = 0

    @property
    def x0(self) -> float: return self.bbox[0]
    @property
    def y0(self) -> float: return self.bbox[1]
    @property
    def x1(self) -> float: return self.bbox[2]
    @property
    def y1(self) -> float: return self.bbox[3]
    @property
    def width(self) -> float: return self.bbox[2] - self.bbox[0]
    @property
    def height(self) -> float: return self.bbox[3] - self.bbox[1]
    @property
    def cx(self) -> float: return (self.bbox[0] + self.bbox[2]) / 2
    @property
    def cy(self) -> float: return (self.bbox[1] + self.bbox[3]) / 2


BODY = "body"
HEADING = "heading"
SUBHEADING = "subheading"
TITLE = "title"
LIST_ITEM = "list"
TABLE = "table"
FOOTNOTE = "footnote"
CAPTION = "caption"
PAGEBREAK = "pagebreak"


@dataclass
class Para:
    kind: str
    text: str
    lines: List[Line] = field(default_factory=list)
    conf: float = 1.0
    flags: List[str] = field(default_factory=list)
    level: int = 0

    @property
    def page(self) -> int:
        return self.lines[0].page if self.lines else 0

    @property
    def n_lines(self) -> int:
        return len(self.lines)


@dataclass
class PageInfo:
    number: int
    width: float
    height: float
    lines: List[Line] = field(default_factory=list)
    source: str = "digital"
    notes: List[str] = field(default_factory=list)


@dataclass
class DocResult:
    paras: List[Para] = field(default_factory=list)
    pages: List[PageInfo] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
