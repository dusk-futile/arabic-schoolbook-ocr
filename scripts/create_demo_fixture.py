from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

from arabic_schoolbook_ocr.persistence import atomic_write_json
from arabic_schoolbook_ocr.pipeline import sha256_file
from arabic_schoolbook_ocr.rendering import DocxDocumentRenderer
from arabic_schoolbook_ocr.schemas import (
    BlockType,
    BoundingBox,
    CanonicalBlock,
    CanonicalDocument,
    CanonicalPage,
    TableCell,
    TableData,
)

DEMO_ROOT = ROOT / "examples" / "demo"
SOURCE_ROOT = DEMO_ROOT / "source"
OUTPUT_ROOT = DEMO_ROOT / "output"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        [
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"),
        ]
        if bold
        else [
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"),
        ]
    )
    selected = next((path for path in candidates if path.is_file()), None)
    if selected is None:
        raise RuntimeError("No Arabic-capable fixture font is installed")
    return ImageFont.truetype(str(selected), size)


def rtl_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    selected_font: ImageFont.FreeTypeFont,
    *,
    fill: str = "#172033",
) -> None:
    visual_text = get_display(arabic_reshaper.reshape(text))
    draw.text(
        position,
        visual_text,
        font=selected_font,
        fill=fill,
        anchor="ra",
    )


def block(
    block_type: BlockType,
    bbox: tuple[int, int, int, int],
    order: int,
    text: str,
    *,
    table: TableData | None = None,
    source_crop: str | None = None,
) -> CanonicalBlock:
    x, y, width, height = bbox
    return CanonicalBlock(
        block_type=block_type,
        bbox=BoundingBox(x=x, y=y, width=width, height=height),
        reading_order=order,
        literal_text=text,
        unicode_normalized_text=text,
        confidence=1.0,
        table=table,
        source_crop=source_crop,
        unresolved=False,
        evidence={"fixture": "project-authored synthetic public demo"},
    )


def main() -> None:
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    page = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(page)
    draw.rectangle((0, 0, 1240, 105), fill="#08747b")
    rtl_text(draw, (1160, 69), "العلوم — صفحة تجريبية مفتوحة", font(32, bold=True), fill="white")
    rtl_text(draw, (1120, 190), "درس تجريبي: الماء والطاقة", font(45, bold=True), fill="#075a62")
    draw.line((115, 225, 1120, 225), fill="#b9dedd", width=3)

    heading = "أولًا: ملاحظات قصيرة"
    paragraph = (
        "الماء مورد مهم في حياتنا. تتغير حالته عند التسخين أو التبريد دون أن يتغير رمزه H2O."
    )
    rtl_text(draw, (1110, 295), heading, font(30, bold=True))
    rtl_text(draw, (1110, 350), paragraph, font(25))
    rtl_text(draw, (1110, 405), "افتح Chapter 3 ثم أجب عن الأسئلة الآتية.", font(25))
    bullets = ["• درجة الحرارة 25°C.", "• سرعة الماء 10 m/s.", "• النسبة 50% من 200."]
    for index, text in enumerate(bullets):
        rtl_text(draw, (1090, 485 + index * 52), text, font(24))

    figure = Image.new("RGB", (360, 300), "white")
    figure_draw = ImageDraw.Draw(figure)
    figure_draw.ellipse((80, 35, 280, 235), outline="#08747b", width=7)
    figure_draw.polygon([(180, 70), (230, 190), (130, 190)], fill="#dff2f1", outline="#08747b")
    figure_draw.line((180, 0, 180, 70), fill="#b96912", width=7)
    figure_draw.arc((18, 20, 340, 285), 195, 340, fill="#b96912", width=7)
    figure_path = SOURCE_ROOT / "energy-cycle.png"
    figure.save(figure_path)
    page.paste(figure, (120, 510))
    rtl_text(draw, (480, 845), "شكل (1): دورة طاقة مبسطة", font(21), fill="#5d6972")

    question = "سؤال 1: اذكر مثالًا واحدًا على تغير حالة الماء."
    rtl_text(draw, (1110, 760), question, font(27, bold=True))
    rtl_text(draw, (1110, 825), "الإجابة: ____________________________________", font(24))

    table_x, table_y, table_w, row_h = 120, 1010, 1000, 115
    widths = [300, 400, 300]
    x_positions = [table_x]
    for width in widths:
        x_positions.append(x_positions[-1] + width)
    for row in range(4):
        draw.line(
            (table_x, table_y + row * row_h, table_x + table_w, table_y + row * row_h),
            fill="#33434a",
            width=3,
        )
    for x in x_positions:
        draw.line((x, table_y, x, table_y + row_h * 3), fill="#33434a", width=3)
    headers = ["النتيجة", "النشاط", "الرقم"]
    rows = [["بخار", "تسخين الماء", "1"], ["ماء سائل", "تبريد البخار", "2"]]
    for column, value in enumerate(headers):
        rtl_text(draw, (x_positions[column + 1] - 25, table_y + 70), value, font(25, bold=True))
    for row_index, values in enumerate(rows, start=1):
        for column, value in enumerate(values):
            rtl_text(
                draw,
                (x_positions[column + 1] - 25, table_y + row_index * row_h + 70),
                value,
                font(24),
            )
    rtl_text(draw, (620, 1685), "1", font(22), fill="#5d6972")

    page_path = SOURCE_ROOT / "synthetic_schoolbook_page.png"
    page.save(page_path)
    page.convert("RGB").save(
        SOURCE_ROOT / "synthetic_schoolbook.pdf",
        format="PDF",
        resolution=150.0,
    )
    table = TableData(
        rows=3,
        columns=3,
        cells=[
            TableCell(row=row, column=column, text=value)
            for row, values in enumerate([headers, *rows])
            for column, value in enumerate(reversed(values))
        ],
    )
    blocks = [
        block(BlockType.CHAPTER_TITLE, (120, 130, 1000, 90), 0, "درس تجريبي: الماء والطاقة"),
        block(BlockType.HEADING_2, (700, 250, 410, 65), 1, heading),
        block(
            BlockType.BODY_PARAGRAPH,
            (490, 320, 620, 125),
            2,
            paragraph + "\n" + "افتح Chapter 3 ثم أجب عن الأسئلة الآتية.",
        ),
        block(BlockType.BULLET_LIST, (500, 455, 590, 175), 3, "\n".join(bullets)),
        block(BlockType.QUESTION, (500, 720, 610, 120), 4, question),
        block(BlockType.FIGURE, (120, 510, 360, 300), 5, "", source_crop="source/energy-cycle.png"),
        block(BlockType.CAPTION, (120, 815, 360, 55), 6, "شكل (1): دورة طاقة مبسطة"),
        block(BlockType.TABLE, (120, table_y, table_w, row_h * 3), 7, "", table=table),
        block(BlockType.PAGE_NUMBER, (590, 1640, 60, 40), 8, "1"),
    ]
    canonical_page = CanonicalPage(
        page_number=1,
        width=page.width,
        height=page.height,
        source_image="source/synthetic_schoolbook_page.png",
        blocks=blocks,
    )
    document = CanonicalDocument(
        title="Synthetic Arabic schoolbook demo",
        source_filename="synthetic_schoolbook_page.png",
        source_sha256=sha256_file(page_path),
        classification="PUBLIC_DEMO",
        pages=[canonical_page],
        run_configuration={"fixture": True, "training_approved": False},
    )
    atomic_write_json(DEMO_ROOT / "canonical_document.json", document)
    renderer = DocxDocumentRenderer()
    renderer.render_docx(document, OUTPUT_ROOT / "demo_literal.docx")
    renderer.render_docx(document, OUTPUT_ROOT / "demo_polished.docx", polished=True)
    print(page_path)


if __name__ == "__main__":
    main()
