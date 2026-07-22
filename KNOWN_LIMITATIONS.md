# Known limitations

- No human-verified ground truth exists yet, so CER and WER are intentionally unreported.
- The optional Gemini agents have deterministic contract tests but no private-page run because explicit upload consent and process-local credentials were not supplied.
- The supplied PDF's embedded text layer is corrupt and cannot bootstrap annotations without visual review.
- Only one private target-domain book exists; it cannot simultaneously represent training, validation, test, and acceptance.
- The supplied document appears to be university lecture material rather than a representative multi-grade schoolbook collection.
- The official Unlimited-OCR baseline was not run because local VRAM is below the official minimum.
- Windows OCR and Local Paddle results are not accuracy estimates until compared with human ground truth.
- Arabic-Img2MD source-work licenses are not documented per item.
- SARD is blocked by non-commercial/no-derivatives and source redistribution terms.
- OpenITI's exact image/XML repository license is missing.
- Complex nested tables, formulas, handwriting, ornate pages, and damaged scans need manual review.
- The DOCX rendered-PDF acceptance step needs a local LibreOffice/Word renderer; it never falls back to a cloud converter.
- The ten-page formatting audit is `NEEDS_CORRECTION`: current real-book pages are top-compressed and table/figure scale and vertical placement are not source-faithful.
- Docker Local mode omits the Windows verifier and currently runs Paddle on CPU unless an operator builds a compatible GPU image.
- The review UI edits text, block type, order, and missing blocks, but polygon-level annotation remains JSON-based.
- No duplicate-detection pipeline, gradient-boosted boundary classifier, LoRA adapter, or trained checkpoint exists.
