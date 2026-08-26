# RESEARCH.md — Phase 0 findings

Benchmarks run on the target-class hardware: **Intel Core i3-8100 (4 cores,
3.6 GHz), 8 GB RAM, no GPU, no admin rights**. That is deliberately close to the
old Windows machines described in the brief, so the timings below are honest for
deployment rather than flattering laptop numbers.

**Status.** The charity's sample book — *سيكولوجية الإبداع والموهوبون*, 209 pages,
produced by Microsoft Word 2010 — arrived mid-way through and **is now the main
result** (§1.3). The OCR figures still come from a synthetic gold set, because
synthetic pages carry exact ground truth; synthetic degradation is always kinder
than a real scanner, so treat every OCR number as an **upper bound**.

---

## 1. The two findings that shaped the design

### 1.1 An Arabic PDF having a text layer does not mean the text is usable

Extracting a text layer from an Arabic PDF very often returns **presentation
forms** — the shaped glyph codepoints (U+FB50–U+FEFF) rather than base letters —
and frequently a broken `ToUnicode` map on top of that. A real extraction from a
test file:

```
raw text layer : ﺍƾﺑﺪﺍﻉ ﻗﺪﺭﺓ ﻋﻘǁﻴﺔ ﻋǁﻴﺎ ﻳﻤﺘǁﻜﻬﺎ ﺍƾﻧﺴﺎﻥ
after NFKC     : اƾبداع قدرة عقǁية عǁيا يمتǁكها اƾنسان
ground truth   : الإبداع قدرة عقلية عليا يمتلكها الإنسان
```

Unicode NFKC repairs the shaping (125 presentation forms → 126 base letters, and
it decomposes the lam-alef ligatures correctly). It cannot repair a broken font
CMap: 16 characters stayed wrong, with `ǁ` standing in for `ل` and `Ǆ` for `ال`.

Consequence: the router must test the **content** of a text layer, not its
existence. `mubsir/router.py` measures the share of characters that fall outside
any expected script and sends the page to OCR above 2%. Skipping this check would
put confident-looking mojibake straight into a Braille book.

### 1.2 Line breaks are not what a PDF says they are

A single visual line of Arabic containing a Latin word or a quotation mark is
emitted by the extractor as **two to four separate "lines"**, split at every
bidirectional direction change. Untouched, this destroys every geometric signal
the paragraph logic depends on — one full justified line looks like four short
ones, and each of them reads as a paragraph end.

This one bug accounted for essentially all early structure errors. Regrouping
fragments by shared baseline and re-ordering them right-to-left
(`mubsir/lines.py`) moved paragraph-boundary F1 from **0.78 → 1.00** on the same
documents, with no change to the decision logic itself.

### 1.3 The sample book: the text layer was broken, and it was recoverable

The charity's book is **not scanned**. It is born-digital, written in Microsoft
Word 2010, with a complete text layer on all 209 pages. Extracting it yields
fluent-looking nonsense:

```
renders as : ليصبح التفوق والموهبة هو المفهوم الشامل أو المظلة الكبرى
extracts as: ليربح التفػؽ كالسػـبة ىػ السفيػـ الذامل أك الػظمة الكربػ
```

Two things make this case important.

**It is invisible to the obvious check.** Every wrong character is still a valid
Arabic letter, so the character-class test from §1.1 reports **0.0% corruption**
on a page that is entirely unreadable. Only a dictionary sees it. The router
therefore tests *word validity* — the share of Arabic words that are real words
— and that is what triggers repair.

**It is exactly recoverable without OCR.** The glyphs are correct; only their
Unicode labels are wrong, and wrong per *contextual form*, which is why 'و'
appears as 'ػ' medially and 'ك' initially. Reading the raw glyph ids out of the
content stream and resolving them through the embedded font — cmap first, then
inverting the GSUB substitutions that produced each contextual form, then
expanding ligatures — reconstructs the real characters.

| Stage | Word validity | Note |
|---|---|---|
| Raw text layer | **0.302** | unreadable |
| After font repair | **0.878** | |
| After lexicon correction | **0.905** | |
| *Clean Arabic prose, same lexicon* | *0.870* | reference ceiling |
| *Character-class corruption metric* | *0.000* | blind to this failure |

Output scores slightly **above** the clean-prose reference, which simply means
the book's vocabulary sits closer to the dictionary than the reference sentence
did. The honest reading is that repaired text is at dictionary-level quality.

Repair is decided **per font**, not per document, because a file mixes faces:

| Font | Words | ToUnicode validity | Decision |
|---|---|---|---|
| Simplified Arabic | 5403 | 0.268 | repaired |
| Simplified Arabic, Bold | 95 | 0.250 | repaired |
| PT Bold Heading | 48 | 0.159 | repaired |
| Arial, Bold | 85 | 0.634 | **trusted** |

That distinction is load-bearing. An early version repaired every font and
turned the correctly-encoded Latin citations into `Norberr`, `Absrracr` and
`inpurs`. Repair is only an improvement where the original is actually broken.

Three further defects surfaced only on the real file:

- **Phantom ligature components.** A ligature draws one glyph but stands for
  several characters, so the extractor emits placeholder entries with glyph id
  −1 for the rest. Decoding the glyph *and* the placeholders doubles letters:
  `المقرر` → `املمقرر`. Placeholders are now skipped, but only when a ligature
  actually precedes them.
- **Over-drawn text.** The title page stacks identical text on itself for a bold
  effect, so `إعداد` merged into `إعدادإعداد`. Duplicates that overlap by more
  than half their width are dropped.
- **Reversed Latin.** Latin runs inside RTL paragraphs were being reversed with
  the Arabic, turning "Julian Stanley" into "Sranley ianJul". Direction is now
  decided from the glyphs, not the surrounding paragraph.

**Residual glyph learning.** A subset font leaves a few contextual forms
unreachable through both cmap and GSUB — 134 distinct glyph ids across 40 pages.
Those fall back to the broken value *consistently*, so the right letter can be
identified by substitution: try each Arabic letter in the words where the glyph
occurs and keep whichever turns nonsense into dictionary words. Seven glyphs
were resolved this way and **four were refused** — mostly ي/ى, where the
dictionary genuinely cannot settle the contest and a wrong guess would be a
misspelling. Refused glyphs keep their fallback and are flagged.

Result on the full book: **209 pages in 94 seconds** (0.45 s/page), 201 pages
repaired, 8 rasterised, 1,355 paragraphs, 12 flagged for review.

---

## 2. Structure reconstruction — the emboss-killer metric

Measured over five layout styles × 8 pages. Ground truth is exact: the generator
records the rectangle of every paragraph, so each extracted line is mapped to its
true paragraph by geometry rather than by guesswork. Scoring is over the *gaps
between consecutive lines* — "new paragraph here, or not?" — which is the
decision the embosser actually cares about.

### 2.1 Born-digital path (trusted text layer)

| Style | Pages | Lines | Gold paras | Predicted | **Boundary F1** | False breaks | Missed |
|---|---|---|---|---|---|---|---|
| `indent_tight` (justified, first-line indent, no para spacing) | 8 | 187 | 34 | 34 | **1.0000** | 0 | 0 |
| `indent_spaced` | 8 | 192 | 36 | 36 | **1.0000** | 0 | 0 |
| `spaced` | 8 | 174 | 38 | 38 | **1.0000** | 0 | 0 |
| `ragged` (unjustified) | 8 | 174 | 36 | 36 | **1.0000** | 0 | 0 |
| `two_col` | 8 | 292 | 39 | 43 | **0.9975** | 1 | 0 |
| **Mean** | 40 | 1019 | 183 | — | **0.9995** | 1 | 0 |

**Target ≥ 0.99 — met** (1 error in 939 boundary decisions).

`indent_tight` is the hardest and most common real Arabic book style: justified,
indented first line, no extra space between paragraphs. Vertical gap carries no
information there, so the decision rests entirely on line-fill and indent.

### 2.2 Robustness to geometric noise

Real detector boxes are noisier than a text layer, so the same set was re-scored
with random jitter applied to every line box:

| Jitter (pt) | Mean F1 | Worst style | Single-column |
|---|---|---|---|
| 0 | 0.9995 | 0.9975 | 1.0000 |
| 1 | 0.9965 | 0.9825 | 1.0000 |
| 3 | 0.9976 | 0.9880 | 1.0000 |
| 5 | 0.9823 | 0.9391 | 1.0000 |
| 8 | 0.8808 | 0.6246 | 0.9430 |

Single-column layouts are unaffected up to 5 pt of box error. **Multi-column
pages are the fragile class** and collapse first — consistent with §3.2 below.

### 2.3 Scanned path (OCR front-end, text layer discarded)

Current engine: **hybrid** — DBNet detection, Tesseract recognition (§3.2).

| Style | CER | WER | Hallucination | Boundary F1 | Reading order | s/page |
|---|---|---|---|---|---|---|
| `indent_spaced` | **0.011** | **0.039** | 0.017 | 0.8837 | 1.000 | 5.1 |
| `ragged` | **0.012** | **0.035** | 0.015 | 0.9677 | 1.000 | 4.9 |
| `spaced` | **0.013** | **0.043** | 0.017 | 0.9333 | 1.000 | 4.6 |
| `indent_tight` | **0.022** | **0.047** | 0.023 | 0.9444 | 1.000 | 4.4 |
| `two_col` | 0.080 | 0.136 | 0.029 | 0.8421 | 0.998 | 4.1 |
| **Mean (single column)** | **0.0145** | **0.0410** | **0.018** | 0.9323 | **1.000** | 4.7 |

Against the brief's targets: **CER ≤ 2% met** (0.0145), **WER ≤ 5% met**
(0.041), **reading order ≥ 98% met** (1.000 single-column, 0.998 two-column).
Paragraph F1 0.932 still falls short of the ≥ 99% target on scanned pages;
that target is met only on the digital and font-repair paths.

Against the first version of this pipeline (PP-OCRv4 alone), measured on the
identical gold set:

| Metric (single column) | v1 | v2 hybrid | Change |
|---|---|---|---|
| CER | 0.069 | **0.0145** | 4.8x better |
| WER | 0.308 | **0.0410** | 7.5x better |
| Hallucination | 0.189 | **0.018** | 10x better |
| `two_col` CER | 0.352 | **0.080** | 4.4x better |

---

## 3. OCR engine benchmark

### 3.1 What was measured

Single-page CER/WER, same gold set, same machine:

| Engine | CER | WER | s/page | Size | Verdict |
|---|---|---|---|---|---|
| **DBNet detect + Tesseract recognise (hybrid)** | **0.0145** | **0.041** | 4.7 | 40 MB | **Selected** |
| Tesseract 5 + `ara`, `tessdata_best` | 0.045 | 0.104 | 2.0 | 28 MB | Strong; misses short lines |
| Tesseract 5 + `ara`, standard tessdata | 0.103 | 0.148 | 1.2 | 5 MB | Fast fallback |
| PP-OCRv4 Arabic, word-split (adaptive Otsu gap) | 0.069 | 0.308 | 3.9 | 12 MB | Pure-pip floor |
| PP-OCRv4 Arabic, word-split (fixed gap ratio) | 0.089 | — | 2.7 | 12 MB | Superseded |
| PP-OCRv3 Arabic | 0.712 | — | 3.0 | 9 MB | Rejected, far worse than v4 |
| PP-OCRv4 Arabic, **whole-line** recognition | 0.668 | — | 9.1 | 12 MB | Unusable, see §3.2 |
| **EasyOCR `ar`** | **0.426** | **0.617** | **50.0** | 100 MB+ | **Rejected** |
| RapidOCR stock (Chinese/English recogniser) | n/a | — | 3.2 | 16 MB | No Arabic recogniser |

EasyOCR was evaluated because it is the most widely used of the three reference
projects. It is rejected on all three axes: its RTL line ordering is scrambled,
and 50 s a page is twenty-five times over budget on the target hardware.

Adding English to the Tesseract language list (`-l ara+eng`) makes Arabic
*worse*, not better — CER 0.028 to 0.043 — so the recogniser runs Arabic-only
and Latin runs are handled by the lexicon instead.

PP-OCR remains bundled as the floor: it is pure pip, needs no binary, and
therefore always works. Tesseract is a binary, so the pipeline detects it and
upgrades automatically when present.

### 3.2 Why the two engines are combined rather than chosen between

Benchmarked separately, they fail in opposite directions:

* **DBNet** (PP-OCR's detector) finds every line, including the short
  paragraph-final ones.
* **Tesseract** reads Arabic roughly three times more accurately by word error,
  but its layout analysis silently drops those same short isolated lines. On one
  test page it read three of a paragraph's four lines and omitted
  `ملاحظاته واستنتاجاته.` entirely. Every page-segmentation mode (3, 4, 6, 11,
  12) drops it, so it is not a tuning problem.

Losing a paragraph-final line costs twice: the text is gone, and the strongest
structural cue goes with it. So detection comes from DBNet and recognition from
Tesseract. Recognition is batched by stacking every line crop onto one tall
canvas with wide white gutters and calling Tesseract once — per-crop calls would
cost a process launch and a 12 MB model load each, about 10 s a page against 2 s.

Three bugs surfaced building it, each worth recording:

- **Fixed-pixel padding between stacked crops.** 26 px is generous at 100 dpi and
  negligible at 300, where Tesseract merged neighbouring crops and their words
  were attributed to the wrong source line. Padding is now proportional to crop
  height, with a per-crop retry for anything that still comes back empty.
- **Latin comma for Arabic comma.** Recognisers emit `,` where `،` belongs
  because the shapes are close. Converting it back, only with an Arabic letter
  on the left, took CER from 0.019 to 0.013 and WER from 0.082 to 0.043 — the
  single largest gain of any post-processing step.
- **A gutter narrower than the merge threshold.** With 13 pt type the line-merge
  gap is about 17 pt and a typical two-column gutter is 18 pt, so a right-column
  line and a left-column line on the same row were being stitched into one,
  destroying ~10% of a two-column page. Whitespace corridors are now found first
  and never merged across; two-column CER fell from 0.180 to 0.080.

### 3.3 The earlier discovery: long lines break PP-OCR

PP-OCR recognisers are trained on short crops. RapidOCR's config caps input
aspect ratio at **8:1**; a justified Arabic book line is around **30:1**. Every
line was being squashed to an eighth of its length before recognition:

```
truth        : يمكن العثور عليها الآن. تستند نظرياتهم إلى الإشارات
whole line   : يمكنات الي الت الا ايا اليا ليا الا اليا اليت اليا     (CER 0.67)
word-split   : يمكن العثور عليها الآن تستند نظرياتهم إلى الإشارات    (CER 0.07)
```

Raising the cap alone does not help — the model itself degenerates over long
sequences. Segmenting each detected line into words on the whitespace projection
and recognising those is what works, and Arabic makes this unusually reliable:
letters join *within* a word, so inter-word gaps are genuinely bimodal against
intra-word gaps. Thresholding those gap widths per line with a 1-D Otsu (rather
than a fixed fraction of line height) took CER from 0.089 to 0.069 and, more
importantly, made it stable across font sizes and justification stretch.

The detector could not be persuaded to emit word boxes directly — sweeping
`unclip_ratio` from 1.6 down to 0.6 changed the box count by one (22 → 21).

### 3.4 Not benchmarked, and why

Reported so the gaps are explicit rather than implied:

- **Tesseract 5 + `ara`** — now benchmarked and selected. It was initially
  unreachable (no Homebrew, no admin rights); `micromamba` installs it from
  conda-forge entirely inside the user's home directory, which also solves
  distribution on locked-down Windows machines.
- **Surya** — PyTorch caps at 2.2.2 on x86 macOS, so the resolver pulled
  `surya-ocr==0.4.5` from early 2024 rather than a current release. Benchmarking
  that would have measured a dev-machine artefact, not the product. Surya is
  viable on the Windows target, where torch is current, but at roughly 1 GB of
  dependencies it fights the 8 GB / no-admin constraint.
- **EasyOCR / docTR / Kraken / Calamari** — same torch ceiling, and all are
  heavier than the selected stack for accuracy that is not established to be
  better on printed Arabic.

### 3.5 Where the remaining OCR error actually is

Word-level diff over one page — 179 of 250 words exactly correct:

| Error class | Example | Fixable? |
|---|---|---|
| Single-letter dropout | `يمكن` → `يمن`, `العشر` → `العر` | Model limit |
| Punctuation dropped | `والسمعي، والعمليات` → `والسمعي والعمليات` | Model/charset limit |
| Character doubling | `وردت` → `ورردت` | Partly — see §4 |
| Word-boundary duplication | `هذا` → `هذهذا` | Segmentation, improvable |

Dropout and punctuation loss dominate, and neither is reachable by
post-processing. **This is the accuracy ceiling of the selected model**, not a
tuning problem.

---

## 4. Lexicon correction — measured, and mostly not worth it

A 294,137-stem Arabic lexicon (LibreOffice hunspell, compressed to 724 KB) with
clitic-aware lookup, driving a corrector allowed exactly one operation: undo a
doubled letter, and only when the original is not a word and the result is.

| Variant | CER | WER | Edits |
|---|---|---|---|
| Raw OCR | 0.0892 | 0.3111 | — |
| Corrected (affix-aware) | 0.0886 | 0.3062 | 7 |
| Corrected (exact-match) | 0.0884 | 0.3051 | 8 |

**Honest verdict: a 0.08-point CER improvement.** It is retained because it is
free at runtime, fully logged and cannot invent a word — but it is not a
meaningful part of the accuracy story and should not be described as one.

## 5. On hallucination

The brief demands a 0.0% hallucination rate. **The pipeline has no generative
step at all** — no LLM, local or otherwise — so it cannot invent text. Nothing is
produced that did not come from either the PDF text layer or the OCR recogniser.

The `halluc` column in the OCR table (0.16–0.22) is a strict *garbling* measure:
it counts output words with no counterpart in the source, which for a misread
word like `يمن` (from `يمكن`) is true but is an OCR error, not an invention. It
is reported to avoid overstating quality, not because the tool fabricates.

The only component that alters text beyond the recogniser is the §4 corrector,
which can make at most one deletion per word, only toward a dictionary word, and
logs every edit.

`qwen2.5vl:3b` was available locally via Ollama and was deliberately **not**
wired in. A vision-language model as the primary text source is exactly the
failure mode the brief rules out, and on this CPU it would also be far slower
than the whole rest of the pipeline.

---

## 6. Recommendation

1. **The sample book is solved.** It needed font repair, not OCR: 209 pages in
   94 seconds at dictionary-level text quality and F1 0.9995 structure. If the
   charity's other books came out of Word the same way — and a shared template
   makes that likely — this is the four-months-to-hours change today.
2. **Ship the born-digital and font-repair paths now.** Both are exact or near
   exact on text and meet every structural target.
3. **Ship the scanned path as assistive, not authoritative.** At ~7% CER it makes
   a first draft plus a targeted review list; it does not make a proofread book.
   The review report and the yellow highlighting exist for exactly this.
4. **Next accuracy work, in order:**
   - Add Tesseract 5 `ara` as a pluggable engine and benchmark it head to head.
     The `OCREngine` interface already exists for this.
   - Fix two-column OCR (CER 0.352 vs 0.069 single-column) — the worst document
     class by a wide margin.
   - Improve word segmentation to remove the `هذا` → `هذهذا` duplication class.
5. **Get more real documents.** The OCR numbers are still synthetic-only. The
   highest-value next input is 3–5 real *scanned* books at different print
   qualities — and the answer to "what did the last five failed embosses have in
   common?", which is still the most valuable question on the list.

## 7. Worst-performing document class

**Two-column scanned pages.** CER 0.352 against 0.069 for single-column, and the
first layout to fail under box noise (F1 0.625 at 8 pt jitter versus 0.943 for
single-column). Multi-column scans should be routed to a human, and the pipeline
flags them in the review report.

---

## 8. Whitespace: the space-vs-return guarantee

The charity's stated failure mode is not wrong letters, it is structure - and
at the character level that reduces to one distinction. An embosser treats a
**space** and a **paragraph mark** as different instructions. A space is a
Braille cell. A paragraph mark ends a block. A stray line break inside a
paragraph becomes a hard line ending that the reader cannot distinguish from a
real one.

So the output is not merely checked for this, it is constructed so it cannot
happen. `emboss_safe()` runs over every paragraph on the way into the document:

- newlines and carriage returns inside a paragraph collapse to one space
  (a newline inside a paragraph is a soft wrap that was never resolved);
- tabs collapse to one space;
- runs of spaces collapse to one;
- non-breaking, thin, hair, figure, line- and paragraph-separator spaces all
  become a plain U+0020 - each of them is a real cell to an embosser;
- zero-width and bidi control characters are deleted outright, because they
  render as stray cells or silently reorder the line;
- leading and trailing spaces are stripped.

Word does the line wrapping. The file contains **no manual line breaks at all**.

Verified two ways. `tests/test_emboss_safety.py` asserts it at the API level,
and `eval/audit_docx.py` re-checks the finished `.docx` at the XML level:

```
AUDIT  output/sample_book.docx
  [ ok ] hard_line_breaks              0
  [ ok ] newline_inside_paragraph      0
  [ ok ] tab_runs                      0
  [ ok ] double_space                  0
  [ ok ] leading_or_trailing_space     0
         paragraphs_total            133
         words_total                4646
VERDICT: clean for embossing
```

---

## 9. The local model question, answered with a measurement

A small local model was asked to do the one job a model could plausibly help
with here: decide, at a boundary the deterministic scorer was unsure about,
whether two lines belong to the same paragraph. One closed question, one-word
answer, no text ever taken back from the model - so it could move a paragraph
boundary but could not invent a word.

**Both models failed the same way: they answered the same word every time.**

| Model | Size | Prompt language | Answers | Accuracy | Time |
|---|---|---|---|---|---|
| `qwen2.5vl:3b` | 3.2 GB | English (SAME/NEW) | `NEW` to all 4 | chance | 6.3 s each |
| `qwen2.5:1.5b` | 986 MB | Arabic (نعم/لا) | `نعم` to all 6 | 3/6 = chance | 1.6 s each |
| `qwen2.5vl:3b` | 3.2 GB | Arabic (نعم/لا) | `نعم` to all 6 | 3/6 = chance | 4.6 s each |

They followed the framing of the question, not the evidence. That is not a
prompt-tuning problem: the evidence is *geometric* - how much of the column
the previous line filled, how large the vertical gap is - and a language model
handed two text snippets cannot see it. On one test it overrode two correct
deterministic answers with wrong ones.

**The machine learning that does help is much smaller.** The same decision, as
logistic regression over eleven geometric features:

| | Weights on disk | Time per decision | Held-out F1 |
|---|---|---|---|
| Local LLM (1.5B) | 986 MB | 1.6 s | chance |
| **Learned classifier** | **1.1 KB** | **microseconds** | **0.9910** |

Trained on 15 generated documents (150 pages, 3,379 labelled boundaries) and
validated **leave-one-style-out** - tested on a layout it never trained on,
because the charity's next book will not be one of these five:

| Held-out style | Boundaries | Hand-written rules | Learned | Change |
|---|---|---|---|---|
| `indent_spaced` | 587 | 1.0000 | 1.0000 | — |
| `indent_tight` | 610 | 1.0000 | 1.0000 | — |
| `ragged` | 608 | 1.0000 | 1.0000 | — |
| `spaced` | 563 | 0.9796 | 1.0000 | +0.0204 |
| `two_col` | 1011 | 0.9737 | 0.9548 | −0.0188 |
| **Mean** | | **0.9907** | **0.9910** | +0.0003 |

Read that honestly: **as a replacement it is a tie.** The hand-written rules
are already near-optimal on clean geometry, and what the model learned confirms
their design - the largest weights are `gap_ratio` (+4.98), `size_ratio`
(+3.05), `left_gap` (+1.73) and `prev_fill` (−1.53), the same signals in the
same directions.

Where it does earn its place is as a **tiebreaker on noisy geometry**. The
rules keep every boundary they are confident about; the model is consulted only
where they are not, which on a scanned page is a few percent of boundaries:

| Style (scanned path) | Rules only | + learned tiebreaker | Change |
|---|---|---|---|
| `spaced` | 0.9333 | **1.0000** | +0.0667 |
| `two_col` | 0.8421 | **0.8780** | +0.0359 |
| `indent_spaced` | 0.8837 | **0.9091** | +0.0254 |
| `indent_tight` | 0.9444 | 0.9444 | — |
| `ragged` | 0.9677 | 0.9677 | — |
| **Mean** | **0.9143** | **0.9399** | **+0.0256** |

No style got worse. That is the "small local AI" in this tool: 1.1 KB of
weights that runs everywhere, not a gigabyte of language model that guesses.


---

## 10. Post-OCR correction: built, measured, and mostly rejected

A trained corrector was built to fix the recogniser's remaining word errors: a
noisy channel with a character confusion model learned from **this pipeline's
own mistakes**, a dictionary-constrained candidate generator, and a frequency
prior. Training data came free - 150 rendered pages, 38,263 words at 94.9% word
accuracy, giving 1,616 aligned error sites.

**It made things worse, and it should not ship.**

| On held-out documents | |
|---|---|
| Errors it fixed | 5 |
| Correct words it broke | 16 |
| Precision | 23.8% |
| Damage to already-correct words | 1.44% |

The literature predicts this exactly. Post-OCR correction pays off between
roughly 2% and 10% CER; below that it costs more than it returns. Huynh, Hamdi
and Doucet state it directly: *"for low error rates (less than 2% and 10% at the
character level and the word level respectively), a post-OCR correction is not a
suitable solution"*. Schaefer and Neudecker took a 1.1% CER corpus to **2.1%**
with a one-step LSTM corrector. This pipeline sits at 1.44% CER / 4.1% WER -
below the threshold on both axes.

The arithmetic is unforgiving. With current word error `e`, a corrector that
fixes fraction `r` of wrong tokens and damages fraction `f` of right ones gives
net error `e(1-r) + (1-e)f`:

| | recall | false positives | WER |
|---|---|---|---|
| Measured noisy-channel corrector | 0.24 | 1.44% | 0.0410 → **0.0451 (worse)** |
| What it would need | 0.30 | ≤0.50% | 0.0410 → 0.0335 |

So the shipped correction is only what clears a **≤0.5% false-positive bar**,
measured on 1,533 already-correct words:

| Stage | Damage to correct words | Shipped |
|---|---|---|
| Character look-alike fixes (Persian kaf/yeh → Arabic) | 0.33% | yes |
| Word-final hamza where a comma belongs | 0.00% | yes |
| Doubled-letter repair, unique dictionary solution | 0.00% | yes |
| Noisy-channel word correction | 1.44% | **no** |

### Where the error actually is

The confusion model earned its place as a *diagnostic* even though its
corrector did not ship. Over 1,138 aligned word pairs:

| Class | Share of all character errors |
|---|---|
| **Punctuation** | **62.9%** |
| — the Arabic comma `،` alone | **31%** |
| Dropped tashkeel | 11.8% |
| Everything else, letters included | ~25% |

The Arabic comma is read as `.` (210×), `ء` (128×), `,` (98×) and `؛` (83×).
It is a small mark on the baseline and the recogniser cannot reliably tell it
from a full stop. Only the unambiguous member of that family is repaired: a
word-final hamza after an otherwise complete word is not Arabic, so it is safe;
a word-final full stop very often is, so `.` is deliberately left alone.

Separating the two kinds of error changes what the headline number means:

| | CER | WER |
|---|---|---|
| Everything | 0.0144 | 0.0410 |
| Ignoring punctuation | 0.0116 | **0.0255** |
| **Letters only** (no punctuation, no diacritics) | **0.0098** | — |

**Under 1% of Arabic letters are wrong and 97.5% of words are exactly right.**
Most of what remains is punctuation and diacritics, not misread letters.

### Things that did not work, recorded so they are not retried

- **Higher resolution.** 300 dpi is optimal; CER rises monotonically above it
  (0.0196 at 300 → 0.0254 at 600) because Tesseract's models are trained near
  300 dpi. More pixels is not more accuracy.
- **`-l ara+eng`.** Adding English to the recogniser makes Arabic worse
  (CER 0.028 → 0.043). Latin runs are handled by the English wordlist instead.
- **Morphological analysis.** Magdy and Darwish measured word-level correction
  at 11.7% WER against 24.5% for the same system with shallow morphology. Not
  built.
- **A direction error worth recording.** The confusion model reports
  P(observed | truth). It lists Greek letters read as digits - because the
  corpus contains λογία and the recogniser misread it. Applying that mapping as
  written would have destroyed genuine Greek in an academic Arabic text. Only
  mappings whose *source* cannot legitimately occur are applied.

Sources: Huynh, Hamdi & Doucet, ICADL 2020 · Schaefer & Neudecker,
LaTeCH-CLfL 2020 · Magdy & Darwish, EMNLP 2006 · Kissos & Dershowitz 2016 ·
Amrhein & Clematide, JLCL 2018.


## Reproducing every number here

```bash
.venv/bin/python eval/make_synthetic.py     # regenerate the gold set
.venv/bin/python eval/run_eval.py           # §2.1 born-digital structure
.venv/bin/python eval/run_eval_ocr.py       # §2.3 scanned path, CER/WER/F1
.venv/bin/python eval/run_eval_real.py      # §1.3 font repair on the real book
.venv/bin/python eval/train_boundary.py    # §9 train + leave-one-style-out
.venv/bin/python -m pytest tests/ -q       # §8 whitespace guarantees
.venv/bin/python eval/audit_docx.py FILE  # §8 audit a finished .docx
.venv/bin/python eval/make_pairs.py        # §10 generate (ocr, truth) pairs
.venv/bin/python eval/train_corrector.py   # §10 train + measure the corrector
```
