# Training decision

Decision date: 2026-07-22.

## Current decision

`DO_NOT_TRAIN` and `TRAINING_APPROVED=false`.

No human-corrected ground truth exists yet, so there is no measured residual-error distribution and no defensible estimate of training benefit. The supplied 209-page book is `EVALUATION_ONLY`; it remains excluded from training and validation. SARD and OpenITI are blocked, Arabic-Img2MD is held for source-provenance review, and no modern schoolbook corpus with explicit training permission has been supplied.

Provider selection, preprocessing, geometry, boundary rules, and review tooling must be benchmarked before attributing remaining errors to model capacity.

## Conditions for reconsideration

Recommend a named training experiment only when all of the following are true:

1. human-approved ground truth shows systematic, repeatable errors;
2. provider/preprocessing/rule changes cannot fix them reliably;
3. every training example has a legal source identity and compatible license;
4. an untouched book-family test and private acceptance set are locked;
5. the expected improvement and success metric are stated in advance;
6. available hardware can complete and reproduce the run;
7. the user explicitly approves the exact data manifest and experiment.

The likely first candidate is a small line/paragraph boundary classifier using permissioned annotations. A later Arabic Unlimited-OCR LoRA adapter is only a candidate after compatible data, hardware, baseline metrics, and public-release review exist.

Draft OCR from the private benchmark, even after human correction, remains evaluation evidence and does not become training data without a separate explicit permission change.
