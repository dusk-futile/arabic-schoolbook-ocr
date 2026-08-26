<div dir="rtl">

# مُبصِر — من وثيقة عربية فوضوية إلى ملف Word نظيف

أداة **تعمل دون إنترنت بالكامل**، وبدون حساب، وبدون صلاحيات مدير، تحوّل الكتب
العربية الممسوحة ضوئيًا أو ملفات PDF إلى ملف **Word نظيف ومنسّق** جاهز للقراءة
أو للطباعة بطريقة برايل.

المشكلة التي تعالجها ليست الحروف الخاطئة، بل **البنية**: الفرق بين نهاية سطر
عادية ونهاية فقرة حقيقية. هذا الفرق هو ما يفسد الطباعة البارزة.

## التشغيل

1. انقر نقرًا مزدوجًا على `run.command` (ماك) أو `run.bat` (ويندوز).
2. ستفتح صفحة في المتصفح.
3. اسحب ملف PDF أو صورة، أو ضع الملفات في مجلد `input`.
4. انتظر شريط التقدم.
5. حمّل ملف Word، وملف النص، و**تقرير المراجعة**.

الفقرات غير المؤكدة **مظللة بالأصفر** داخل ملف Word، وتقرير المراجعة يرتّبها
حسب الخطورة. الهدف ليس الكمال، بل أن تعرف أين تنظر.

## ما تفعله الأداة وما لا تفعله

**تفعل:** إعادة بناء الفقرات، حذف ترويسات الصفحات وأرقامها، ترتيب الأعمدة من
اليمين إلى اليسار، **إصلاح ملفات PDF التي يظهر نصها سليمًا وهو في الحقيقة
مشوّه بسبب ترميز الخط**، إخراج Word ونص نظيف.

**لا تفعل:** لا تخترع نصًا. لا يوجد أي نموذج توليدي في الأداة، فلا يمكنها أن
تضيف كلمة لم تكن في المصدر.

</div>

---

## Quick start

```bash
cd mubsir
./setup.sh          # macOS/Linux  (setup.bat on Windows) - one time, no admin
python demo/run_demo.py
```

`setup.sh` installs a private Python, the dependencies, Tesseract 5 and the
models — all inside your home directory, so it works on a locked-down machine.
`run_demo.py` then prints CER, WER, paragraph F1 and reading order measured
against the ground truth in `demo/pages/*.gold.json`.

Convert your own document:

```bash
python -m mubsir yourfile.pdf -o output
```

Or start the offline browser interface and drag a file in:

```bash
python -m mubsir.webui
```


# mubsir — messy Arabic document → clean Word file

A **fully offline**, no-account, no-admin tool that turns scanned Arabic books
and PDFs into a **clean, structurally correct Word document** ready for reading
or for Braille embossing.

The problem it solves is not wrong letters. It is **structure** — telling a soft
line wrap apart from a real paragraph break. That distinction is what ruins an
emboss.

## Run it

1. Double-click `run.command` (macOS) or `run.bat` (Windows). First run installs
   itself; it needs no administrator rights.
2. A page opens in your browser, served from your own machine.
3. Drag in a PDF or image, or drop files into `input/`.
4. Watch the progress bar.
5. Download the Word file, the plain text, and the **review report**.

Uncertain paragraphs are **highlighted yellow** in the Word file, and the review
report ranks them by risk. The tool is not trying to be perfect — it is trying to
make review fast and targeted.

## Command line

```bash
.venv/bin/python -m mubsir book.pdf -o output
.venv/bin/python -m mubsir scans/ --force-ocr --dpi 300
.venv/bin/python -m mubsir book.pdf --no-ocr        # digital text layers only
```

Useful flags: `--engine auto|hybrid|tesseract|ppocr-arabic`, `--force-ocr`,
`--no-ocr`, `--strip-tashkeel`, `--digits western|arabic_indic`,
`--keep-furniture`, `--max-pages N`, `--json`.

## How it works

```
input PDF / images
  │
  ├─[0] router ......... is the PDF's text layer trustworthy?
  │                      Not "does one exist", and not just "is it mojibake" —
  │                      a broken Arabic font maps every letter to a *different
  │                      valid Arabic letter*, so the text looks fine and reads
  │                      as nonsense. The test is dictionary word validity.
  │                      Three outcomes: trust it / repair it / OCR it.
  ├─[1] preprocess ..... deskew, border trim (scanned pages only)
  ├─[2] front-end ...... text layer,  OR  font repair (read raw glyph ids and
  │                      resolve them through the embedded font — exact, no
  │                      OCR),  OR  OCR: DBNet detects every line, Tesseract
  │                      reads them. Each engine covers the other's failure.
  │                      All three emit the same Line objects, so everything
  │                      downstream is tested once.
  ├─[3] line repair .... regroup bidi-fragmented lines by baseline, RTL order
  ├─[4] structure ...... per-column geometry; soft wrap vs paragraph break
  ├─[5] normalise ...... presentation forms → base letters, tatweel, spacing
  ├─[6] lexicon check .. undo doubled-letter OCR artefacts, conservatively
  └─[7] flag ........... rank every paragraph by risk
        ↓
  book.docx (semantic styles, real RTL)  +  book.txt  +  book.review.html
```

## Accuracy — measured, not claimed

Full method and caveats in [RESEARCH.md](RESEARCH.md). Regenerate everything:

```bash
.venv/bin/python eval/make_synthetic.py
.venv/bin/python eval/run_eval.py           # structure, born-digital
.venv/bin/python eval/run_eval_ocr.py       # scanned path: CER / WER / F1
.venv/bin/python eval/run_eval_real.py      # font repair on a real book
```

| Path | Paragraph F1 | CER | WER | Reading order |
|---|---|---|---|---|
| Born-digital text layer | **0.9995** | exact | exact | 1.000 |
| Font-repaired text layer | **0.9995** | 0.905 word validity (clean prose = 0.870) | — | 1.000 |
| Scanned, single column | 0.932 | **0.0145** | **0.041** | **1.000** |
| Scanned, two column | 0.842 | 0.080 | 0.136 | 0.998 |

Targets from the brief: CER ≤ 2% **met**, WER ≤ 5% **met**, reading order
≥ 98% **met**. Paragraph F1 ≥ 99% is met on the digital and font-repair paths
but not on scanned pages (0.932), and two-column scans remain the worst class.

The scanned path improved sharply once the engines were combined rather than
chosen between — DBNet finds every line, Tesseract reads them far more
accurately, and neither alone does both:

| Metric (single column) | first version | now | change |
|---|---|---|---|
| CER | 0.069 | **0.0145** | 4.8x better |
| WER | 0.308 | **0.041** | 7.5x better |
| Hallucination | 0.189 | **0.018** | 10x better |

### The real book

The charity's sample — 209 pages, written in Word 2010 — is **not scanned**. It
has a full text layer that extracts as nonsense because the embedded Arabic
font's character map is broken:

```
renders as : ليصبح التفوق والموهبة هو المفهوم الشامل
extracts as: ليربح التفػؽ كالسػـبة ىػ السفيػـ الذامل
```

Every wrong character is still a valid Arabic letter, so a naive corruption
check scores it **0.0% corrupt** while it is completely unreadable. Reading the
raw glyph ids out of the embedded font instead takes it from **30% to 90% real
Arabic words** — exactly, with no OCR involved. The whole book processes in
**94 seconds**, producing 1,355 paragraphs with 12 flagged for review.

Structure and OCR figures come from a synthetic gold set on target-class
hardware (Intel i3, 8 GB, no GPU); real scans will be worse. The font-repair
figures are from the real book.

## Requirements

Python 3.11, about 350 MB of dependencies and 40 MB of models. No GPU, no admin
rights, no network after setup — Tesseract is installed into your home directory
by `micromamba`, so no administrator is needed on Windows either. Roughly
5 seconds per scanned page and half a second per born-digital page on an 8 GB
machine.

## Layout

```
mubsir/      pipeline: router, preprocess, ocr/, lines, structure, docx_out, webui
eval/        gold-set generator, metrics, and the two evaluation scripts
models/      OCR model (~8 MB) + Arabic lexicon (~0.7 MB)
tools/       one-off builders (lexicon)
input/       drop files here
output/      .docx, .txt, .review.html land here
```

## Licence

This tool lives inside the `arabic-schoolbook-ocr` repository and is
contributed under that repository's **Apache-2.0** licence (see the top-level
`LICENSE`). Third-party components keep their own licences:
PP-OCRv4 Arabic recognition model (Apache 2.0, PaddlePaddle), RapidOCR detection
model (Apache 2.0), the Arabic lexicon derived from the LibreOffice hunspell
dictionary (GPL/LGPL/MPL tri-licence), and an English wordlist derived from
Webster's 2nd International (public domain). See `models/lexicon/SOURCE.md`.
The lexicons are optional: delete them and the tool still runs, minus the
corrector and the residual-glyph learning.
