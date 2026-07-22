# Experiments

## BASELINE-20260722-WINDOWS-OCR

| Field | Value |
|---|---|
| Status | Completed, pre-training |
| Input rights | `EVALUATION_ONLY` |
| Input pages | 4, 36, 53, 184, 209 |
| Render | Ghostscript 10.04.0, 300-DPI grayscale, 2481 x 3508 |
| OCR | Windows.Media.Ocr, `ar-SA` |
| Mean OCR time | 0.7323 s/page |
| Silent failures | 0/5 |
| CER/WER | Not measured; no valid ground truth |
| Raw output | `artifacts/runs/baseline-20260722/windows_ocr_raw.json` |

Observed failure taxonomy: RTL word-order reversal, Arabic-English run-order errors, item-number displacement, table-column separation, and missing figure semantics.

## BASELINE-20260722-PDF-TEXT

| Field | Value |
|---|---|
| Status | Completed, rejected as transcription baseline |
| Engine | pypdf 6.10.0 |
| Coverage | 209/209 pages, 309,136 characters |
| Time | 5.8075 s total, 0.0278 s/page |
| Visual fidelity | 0/5 sampled pages |

Reason for rejection: systematic incorrect Unicode character mapping despite visually correct glyphs.

## UNLIMITED-OCR-BASELINE

| Field | Value |
|---|---|
| Status | Not run - hardware blocked |
| Code revision | `1ab6b46b989ebf26328a968d87ce583a9650ab90` |
| Weight revision | `2a06ebf2d6f600f95fd2b99f6ccdee18a52e3b8f` |
| Required | At least 8 GB VRAM for BF16 per official recipe |
| Available | 6 GB VRAM |
| Weights downloaded | No |

No training experiments exist.
