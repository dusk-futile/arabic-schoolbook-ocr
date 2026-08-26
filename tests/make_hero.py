"""Build the README picture: messy input on the left, a clean Word file on the right.

Produces a still PNG (the one the README leads with) and a short GIF of the
same scene. The Arabic is rendered through PyMuPDF so the shaping is real, and
the "before" text is the actual broken extraction from the sample book rather
than an illustration of one.
"""
from __future__ import annotations

import os

import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PNG = os.path.join(ROOT, "docs", "hero.png")
OUT_GIF = os.path.join(ROOT, "docs", "hero.gif")

W, H = 1240, 620
PAPER_W, PAPER_H = 392, 400
DOC_W, DOC_H = 452, 452
LEFT_X, RIGHT_X = 62, 726
TOP = 74

BG = (247, 248, 250)
INK = (24, 28, 36)
MUTED = (126, 136, 152)
ACCENT = (13, 92, 182)
BAD = (183, 71, 62)
GOOD = (12, 120, 80)

BROKEN = ("ليربح التفػؽ كالسػـبة ىػ السفيػـ الذامل أك السظمة الكربػ التي "
          "تشجرج تحتها جسيع السفاهيم األخخػ، كال يقرج بالتفػؽ كالسػـبة في "
          "هحه الجراسة التحريل الجراسي األكاديسي أك الحكاء، بل التفػؽ "
          "كالسػـبة بذكل شامل في مختمف السجاالت األدائية كاألكاديسية.")

CLEAN = [
    ("h", "الفصل الأول: مفهوم التفوق والموهبة"),
    ("p", "ليصبح التفوق والموهبة هو المفهوم الشامل أو المظلة الكبرى التي "
          "تندرج تحتها جميع المفاهيم الأخرى، ولا يقصد بالتفوق والموهبة في هذه "
          "الدراسة التحصيل الدراسي الأكاديمي أو الذكاء."),
    ("p", "بل التفوق والموهبة بشكل شامل في مختلف المجالات الأدائية "
          "والأكاديمية على حد سواء."),
]

_FONTS = [
    "/System/Library/Fonts/Supplemental/Helvetica.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]


def font(size: int, bold: bool = False):
    for path in _FONTS:
        if os.path.exists(path):
            for idx in ((1, 0) if bold else (0,)):
                try:
                    return ImageFont.truetype(path, size, index=idx)
                except Exception:
                    continue
    return ImageFont.load_default()


def arabic(html: str, css: str, w: int, h: int) -> Image.Image:
    doc = pymupdf.open()
    page = doc.new_page(width=w, height=h)
    page.insert_htmlbox(pymupdf.Rect(0, 0, w, h), html, css=css)
    pix = page.get_pixmap(dpi=220, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    return img.resize((w, h), Image.LANCZOS)


def messy_sheet(seed: int, tilt: float) -> Image.Image:
    css = ("*{font-family:sans-serif;font-size:12.5px;direction:rtl;"
           "text-align:justify;line-height:1.9;color:#242830;}")
    body = arabic(f"<div dir='rtl'>{BROKEN}</div>", css, PAPER_W - 42, PAPER_H - 64)
    sheet = Image.new("RGB", (PAPER_W, PAPER_H), (250, 247, 240))
    sheet.paste(body, (21, 42))
    arr = np.array(sheet).astype(np.int16)
    rng = np.random.default_rng(seed)
    arr += rng.normal(0, 8, arr.shape).astype(np.int16)      # scanner speckle
    arr[:, :12] -= 20                                        # spine shadow
    arr[:16, :] -= 12
    sheet = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    sheet = sheet.filter(ImageFilter.GaussianBlur(0.4))
    return sheet.rotate(tilt, resample=Image.BICUBIC, expand=True,
                        fillcolor=BG)


def messy_stack() -> Image.Image:
    """Three sheets fanned out - "papers", not a tidy single page."""
    canvas = Image.new("RGB", (PAPER_W + 46, PAPER_H + 44), BG)
    for i, (seed, tilt, off) in enumerate([(3, -3.4, (30, 6)),
                                           (5, 2.1, (16, 18)),
                                           (7, -0.6, (0, 30))]):
        s = messy_sheet(seed, tilt)
        shadow = Image.new("RGB", s.size, (214, 214, 218))
        canvas.paste(shadow, (off[0] + 3, off[1] + 3))
        canvas.paste(s, off)
    return canvas


def word_doc(reveal: float = 1.0) -> Image.Image:
    css = ("*{font-family:sans-serif;direction:rtl;color:#1a1e26;}"
           "h2{font-size:16px;text-align:right;font-weight:bold;"
           "margin:0 0 13px 0;line-height:1.55;}"
           "div.p{font-size:13px;text-align:justify;line-height:2.05;"
           "margin:0 0 13px 0;}")
    html = "".join(
        (f"<h2 dir='rtl'>{t}</h2>" if k == "h" else f"<div class='p' dir='rtl'>{t}</div>")
        for k, t in CLEAN)
    body = arabic(html, css, DOC_W - 60, DOC_H - 104)

    doc = Image.new("RGB", (DOC_W, DOC_H), (255, 255, 255))
    doc.paste(body, (30, 84))
    d = ImageDraw.Draw(doc)
    # Word-ish title bar so it reads as a .docx, not "some page"
    d.rectangle([0, 0, DOC_W - 1, 40], fill=(31, 78, 143))
    d.rectangle([10, 10, 30, 30], fill=(255, 255, 255))
    d.text((15, 12), "W", fill=(31, 78, 143), font=font(15, True))
    d.text((38, 12), "book.docx", fill=(255, 255, 255), font=font(14, True))
    d.line([(0, 40), (DOC_W, 40)], fill=(24, 62, 116))
    d.rectangle([0, 0, DOC_W - 1, DOC_H - 1], outline=(214, 220, 230), width=1)
    if reveal < 1.0:
        cut = int(84 + (DOC_H - 96) * reveal)
        d.rectangle([1, cut, DOC_W - 2, DOC_H - 2], fill=(255, 255, 255))
    return doc


def compose(reveal: float = 1.0, pulse: float = 1.0) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    stack = messy_stack()
    img.paste(stack, (LEFT_X, TOP - 4))
    # a soft page shadow under the white document
    d.rectangle([RIGHT_X + 5, TOP + 5, RIGHT_X + DOC_W + 5, TOP + DOC_H + 5],
                fill=(226, 229, 235))
    img.paste(word_doc(reveal), (RIGHT_X, TOP))

    f_lab, f_small, f_title, f_stat = font(18), font(14), font(27, True), font(17, True)

    d.text((LEFT_X, 24), "scans, photos, messy PDFs", fill=MUTED, font=f_lab)
    d.text((LEFT_X, TOP + PAPER_H + 62), "30% real Arabic words", fill=BAD, font=f_stat)
    d.text((LEFT_X, TOP + PAPER_H + 86),
           "no paragraphs  ·  columns interleaved", fill=MUTED, font=f_small)

    d.text((RIGHT_X, 24), "one clean Word file you can edit", fill=MUTED, font=f_lab)
    d.text((RIGHT_X, TOP + DOC_H + 30), "90% real Arabic words", fill=GOOD, font=f_stat)
    d.text((RIGHT_X, TOP + DOC_H + 54),
           "real paragraphs  ·  no stray line breaks", fill=MUTED, font=f_small)

    cx0, cx1 = LEFT_X + stack.width + 26, RIGHT_X - 26
    cy = TOP + DOC_H // 2
    d.text((cx0 + 4, cy - 74), "mubsir", fill=INK, font=f_title)
    d.line([(cx0, cy), (cx1 - 14, cy)], fill=(206, 214, 227), width=3)
    head = cx0 + (cx1 - 14 - cx0) * pulse
    d.ellipse([head - 8, cy - 8, head + 8, cy + 8], fill=ACCENT)
    d.polygon([(cx1 - 14, cy - 10), (cx1, cy), (cx1 - 14, cy + 10)], fill=ACCENT)
    for i, line in enumerate(["fully offline", "no cloud, no account", "~0.5 s per page"]):
        d.text((cx0, cy + 26 + i * 20), line, fill=MUTED, font=f_small)
    return img


def main() -> None:
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    compose().save(OUT_PNG)
    print(f"{OUT_PNG}  {os.path.getsize(OUT_PNG)//1024} KB")

    frames = []
    n = 30
    for i in range(n):
        t = i / (n - 1)
        frames.append(compose(min(1.0, max(0.0, (t - 0.12) / 0.58)),
                              min(1.0, t / 0.72)))
    frames += [frames[-1]] * 14
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=190) for f in frames]
    pal[0].save(OUT_GIF, save_all=True, append_images=pal[1:],
                duration=70, loop=0, optimize=True)
    print(f"{OUT_GIF}  {os.path.getsize(OUT_GIF)//1024} KB")


if __name__ == "__main__":
    main()
