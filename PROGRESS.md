# Progress

Updated: 2026-07-22

## Completed

- Read the supplied operating specification and PDF workflow.
- Audited exact revisions for Arabic-Nougat, Arabic-Img2MD, SARD, Arabic E-Book Corpus, OpenITI Arabic Print Data, and Unlimited-OCR.
- Distinguished repository code, dataset, and model-weight licenses.
- Recorded commercial, redistribution, attribution, share-alike, and source-data restrictions.
- Verified that no candidate training dataset payload or candidate training-model weight has been downloaded; only the audited local Paddle inference models are cached.
- Hashed and inspected the supplied 209-page PDF locally.
- Rendered representative pages and visually inspected the book.
- Ran native PDF extraction and Windows Arabic OCR baselines without external upload.
- Created separate dataset layers, versioning rules, subset proposal, and book-level split policy.
- Implemented Local Paddle, Azure, Hybrid, mock, Windows, and Unlimited preflight providers.
- Implemented canonical page/block/table/boundary/run schemas and page-level checkpoints.
- Implemented semantic RTL/LTR DOCX reconstruction, real tables/figures/lists, and reopen validation.
- Completed and visually reviewed a five-page Local Paddle smoke run without cloud access.
- Built and visually verified the four-screen FastAPI/React application.
- Added a CC0 Arabic public demo, privacy/security governance, container definitions, and CI.
- Completed the authorized checkpointed 209-page Local acceptance run: 209/209 pages, zero page failures, and no cloud calls.
- Generated literal/polished DOCX, canonical JSON, local rendered PDF, review/accuracy reports, and a 30-page private ground-truth draft.
- Verified both DOCX files structurally and confirmed the rendered PDF has exactly 209 pages.
- Technically spot-checked the deterministic 20-page sample, both table pages, and figure-heavy page 188; visible OCR errors remain queued for human review.

## Held or blocked

- Arabic-Img2MD: Hindawi source-work provenance/licensing not documented per item.
- SARD: CC BY-NC-ND and explicit Alukah non-commercial/no-redistribution restriction.
- OpenITI Arabic Print Data: no license in exact image/XML repository.
- Supplied book: acceptance only.
- Unlimited-OCR local baseline: official minimum 8 GB VRAM; local GPU has 6 GB.
- CER/WER: no human-verified ground truth; embedded text layer is corrupted.

## Remaining acceptance work

- Human-correct and explicitly approve all 30 ignored ground-truth pages.
- Calculate CER/WER and structure metrics only after the readiness assertion passes.
- Do not run Azure, Gemini, dataset materialization, or training without the corresponding explicit approval/consent gate.
