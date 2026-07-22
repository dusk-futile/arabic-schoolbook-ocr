# Product requirements

## Objective

Convert Arabic schoolbook PDFs into editable, structurally faithful Word documents while preserving literal content, mixed Arabic-English runs, page structure, review evidence, and privacy choices.

## Primary workflow

1. Upload a PDF locally.
2. Select Local, Cloud Accurate, or Hybrid Verified.
3. Explicitly opt in if any page or crop will be sent to a cloud provider.
4. Watch page-level progress, warnings, retryable failures, API usage, and estimated cost.
5. Review source pages beside canonical blocks and correct uncertain content.
6. Export literal DOCX, optional polished DOCX, canonical JSON, rendered PDF, correction report, and benchmark report when human ground truth exists.

## Non-goals for Phase 2

- Model training or fine-tuning.
- Silent source-content correction.
- Full-book Gemini processing through the standard UI.
- Publishing private books, page images, or annotations.
- Claiming accuracy before human-corrected ground truth exists.

## Acceptance gates

- Unit and mock integration tests pass.
- Six mixed-direction fixtures round-trip in logical Unicode order.
- Five representative pages produce all mandatory local artifacts.
- Literal DOCX reopens, has valid ZIP/XML, and its extracted text matches canonical text after whitespace canonicalization.
- A rendered DOCX PDF is visually inspected before any document is delivered.
- Cloud modes remain unexecuted until both credentials and explicit per-job consent are present.
