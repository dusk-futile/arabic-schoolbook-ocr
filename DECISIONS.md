# Decisions

## D-001 - Private book permission

- Decision: `EVALUATION_ONLY`.
- Consequence: all 209 pages remain in `acceptance_private`; no training, validation, correction learning, or external upload.

## D-002 - SARD

- Decision: blocked.
- Reason: CC BY-NC-ND 4.0 plus explicit Alukah non-commercial/no-redistribution source terms.
- Reversal condition: written permission covering training, derivatives/weights, commercial use, and redistribution, followed by compatibility review.

## D-003 - Arabic-Img2MD

- Decision: hold.
- Reason: GPL-3.0 dataset card does not provide per-work licenses for the Hindawi HTML described in the paper.
- Reversal condition: auditable source-book list and licenses plus a GPL/model-output release decision.

## D-004 - Arabic E-Book Corpus

- Decision: sole green candidate.
- Scope: tokenizer analysis and source text for locally generated synthetic pages under CC BY 4.0 attribution.
- Exclusions: it is not aligned OCR data; fonts/templates/assets need separate audits.

## D-005 - OpenITI Arabic Print Data

- Decision: blocked.
- Reason: exact repository and image/XML payload have no license file; general OpenITI statements are insufficient.

## D-006 - Baseline truth policy

- Decision: do not score against the PDF text layer.
- Reason: its Unicode mapping is visibly corrupted.
- Consequence: CER/WER remain unmeasured until human double-review ground truth exists.

## D-007 - Unlimited-OCR baseline

- Decision: do not download weights on current hardware.
- Reason: 6 GB local VRAM is below the official 8 GB BF16 minimum.
- Consequence: record `NOT_RUN_HARDWARE_BLOCKED`, not a fabricated score.
