# Model card draft

## Model status

No Arabic-adapted model has been trained. There is no checkpoint to release.

## Intended future use

Exact transcription and structured reconstruction of printed Modern Standard Arabic educational books, including mixed English, digits, headings, lists, simple tables, captions, and page boundaries.

## Base model candidate

- `baidu/Unlimited-OCR`
- Weights revision: `2a06ebf2d6f600f95fd2b99f6ccdee18a52e3b8f`
- License: MIT on model card
- Local baseline status: not run; 6 GB VRAM is below the official 8 GB BF16 minimum

## Training data status

- Approved candidate: Arabic E-Book Corpus v1 text, after user approval and asset audit.
- Held: Arabic-Img2MD.
- Blocked: SARD and OpenITI Arabic Print Data.
- Excluded: all private acceptance books.

## Evaluation status

- Five-page Local Paddle + Windows-verifier smoke workflow completed without page failure.
- Literal/polished DOCX structural validation and five-page local PDF rendering passed.
- Checkpointed 209-page Local acceptance processing completed 209/209 pages with zero page failures and no cloud calls.
- Literal/polished DOCX validation passed, and the local rendered PDF has exactly 209 pages.
- The run produced 1,469 canonical blocks, of which 1,457 remain unresolved pending human review.
- CER/WER unavailable pending human double-reviewed ground truth.
- A locked 30-page EVALUATION_ONLY draft/review workflow exists; no page is human-approved yet.
- Known residual failures include recognition/spacing errors, uncertain RTL reading order, mixed bidirectional runs, and complex structures.

## Release status

`NO_TRAINED_MODEL_TO_RELEASE`

The Apache-2.0 application can be prepared for software release independently. Any future trained checkpoint requires compatible-license review, locked book-family splits, verified annotations, baseline comparisons, privacy review, reproducible training evidence, and explicit user approval.
