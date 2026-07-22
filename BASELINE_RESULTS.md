# Baseline results before training

Run date: 2026-07-22. No training was performed and no private page left the computer.

## Evaluation book

| Field | Value |
|---|---|
| Book ID | `psychology-creativity-giftedness-d2a34a23` |
| Rights | `EVALUATION_ONLY` |
| SHA-256 | `d2a34a23cf247382af5990b30b3fe2cf8c19878feb7da6e1fdf2c4343c94f7d2` |
| File size | 3,228,435 bytes |
| Pages | 209 |
| PDF state | Valid PDF 1.5, unencrypted, born-digital, A4 |
| Embedded text | Present on 209/209 pages but systematically mapped to incorrect Unicode characters |

Representative pages were selected by page type rather than cherry-picking OCR quality:

- page 4: normal chapter/paragraph page;
- page 36: questions and numbered list;
- page 53: mixed Arabic-English technical terms;
- page 184: paragraph plus figure/caption;
- page 209: table of contents.

## Baseline 1: native PDF text extraction

Engine: `pypdf 6.10.0`, no OCR.

| Measure | Result |
|---|---:|
| Pages returning text | 209/209 |
| Extracted characters | 309,136 |
| Whole-book extraction time | 5.8075 s |
| Mean extraction time | 0.0278 s/page |
| Visually faithful sampled pages | 0/5 |

The rendered glyphs are correct Arabic, but the PDF's character mapping turns many letters into different Arabic letters. For example, visually correct headings and paragraphs become systematic substitutions in extracted Unicode. Native extraction is therefore unusable as transcription or reference ground truth despite its apparent 100% text coverage.

## Baseline 2: installed Windows Arabic OCR

Engine: `Windows.Media.Ocr`, language `ar-SA`. Input: 300-DPI grayscale page renders, 2481 x 3508 pixels.

| Page | Type | Seconds | Lines | Output characters | Main observation |
|---:|---|---:|---:|---:|---|
| 4 | Paragraph | 0.9281 | 27 | 1,574 | Most words recognizable; word order reversed within every Arabic line |
| 36 | Questions/list | 0.2754 | 7 | 315 | Text recognizable; all four item numbers move to the wrong logical position |
| 53 | Arabic-English | 0.9242 | 25 | 1,402 | Arabic and most English recognized; all six mixed runs have incorrect direction/order; `Intelligence` becomes `lntelligence` |
| 184 | Figure/caption | 1.0462 | 12 | 655 | Body words mostly recognizable; line order is reversed and figure structure is not represented |
| 209 | Table of contents | 0.4875 | 26 | 291 | Captures many cell strings but emits columns separately; 0/7 chapter-topic-page row associations survive |
| **Total/mean** | 5 pages | **3.6614 / 0.7323 per page** | **97** | **4,237** | Not suitable for production output without RTL/layout reconstruction |

Structural checks:

| Check | Result |
|---|---:|
| Pages with correct raw Arabic logical word order | 0/5 |
| Question items with number/text structure preserved | 0/4 |
| Mixed Arabic-English lines with correct run order | 0/6 |
| TOC table rows reconstructed as rows | 0/7 |
| Silent page failures | 0/5 |

## CER and WER status

`CER = NOT_MEASURED`
`WER = NOT_MEASURED`

The embedded PDF text is demonstrably corrupted and cannot serve as ground truth. Scoring against it would produce a misleading number. A human must transcribe and double-review a locked set of page or line regions before CER/WER can be reported. Model consensus is not ground truth.

## Baseline 3: Local Paddle five-page smoke run

Engine: PaddlePaddle 3.2.2, PaddleOCR 3.7.0 Arabic PP-OCRv3, PaddleX 3.7.2 `PP-DocLayout_plus-L`, with local Windows OCR as independent verifier. Pages: 4, 36, 53, 184, and 209. No cloud call and no training.

| Measure | Result |
|---|---:|
| Completed pages | 5/5 |
| Failed pages | 0 |
| Wall-clock time | 97.2 s |
| Unresolved blocks queued for review | 32 |
| Canonical table on page 209 | 9 rows x 3 columns, 24 populated cells |
| Literal DOCX structural validation | Passed |
| Polished DOCX structural validation | Passed |
| DOCX real table count | 1 |
| Missing canonical text after reopen | 0 blocks |

This verifies pipeline operation and artifact integrity, not transcription accuracy. Verifier-only regions on pages 53 and 209 remain explicit human-review evidence rather than silently inserted text.

## Baseline 4: full-book Local acceptance run

Engine and revisions are the same as Baseline 3. The private book was processed locally on CPU with Windows OCR as verifier; no Azure, Gemini, dataset download, or training was used.

| Measure | Result |
|---|---:|
| Source pages accounted for | 209/209 |
| Completed / failed pages | 209 / 0 |
| Canonical blocks | 1,469 |
| Unresolved blocks queued for review | 1,457 |
| First OCR pass | about 4,858.3 s provider-reported; 4,867.2 s runner wall time |
| Checkpoint-only final regeneration | 37.0 s |
| Literal / polished DOCX validation | Passed / passed |
| Missing canonical blocks after DOCX reopen | 0 / 0 |
| Editable tables / embedded figures | 2 / 10 |
| Rendered PDF page count | 209, matching the 209-page source |
| Accuracy | `UNMEASURED_PENDING_HUMAN_GROUND_TRUTH` |

A technical spot-check covered the deterministic random 20-page queue, both table pages, and page 188, whose three narrow figures exposed and then verified a source-scale image-rendering fix. The output is structurally complete, but visible recognition, spacing, and reflow errors remain. Completion is therefore not an accuracy claim.

## Unlimited-OCR baseline status

`STATUS = NOT_RUN_HARDWARE_BLOCKED`

- Local GPU: NVIDIA GeForce GTX 1660 SUPER, 6,144 MiB VRAM.
- Local RAM: approximately 17.1 GB.
- The [official vLLM recipe](https://recipes.vllm.ai/baidu/Unlimited-OCR) requires a single GPU with at least 8 GB VRAM for BF16 inference.
- The official Transformers recipe calls `.cuda()` and the audited environment did not have PyTorch/Transformers or model weights installed.
- No weights were downloaded because the machine does not meet the official minimum. This is a blocked baseline, not a zero score.

Running on a cloud/API would send private page images off-device and is not authorized. A future run requires a compatible local GPU or explicit user approval of a named external environment, data transfer, cost, and credential handling.

## Baseline conclusion

The immediate failure mode is not merely Arabic character recognition. It is the combination of broken PDF Unicode mapping, right-to-left reading order, bidirectional Arabic-English runs, and table reconstruction. The installed local OCR is a useful independent verifier candidate after geometric/RTL post-processing, but it is not a production baseline.

Raw local evidence is stored in ignored paths:

```text
private_data/page_images/psychology-creativity-giftedness-d2a34a23/baseline-300dpi/
artifacts/runs/baseline-20260722/windows_ocr_raw.json
tmp/pdfs/inventory/contact_sheet.png
jobs/book-local-acceptance-20260722/
data/ground_truth/book-local-acceptance-20260722/
```
