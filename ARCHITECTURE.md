# Provider and pipeline architecture

Status: Phase 2 implementation baseline, 2026-07-22. `TRAINING_APPROVED=false`.

## Design constraints

- Local mode is the default and never requires credentials.
- Cloud access is fail-closed. A job must name an allowed provider and carry an explicit `cloud_opt_in=true` consent record before any image bytes leave the machine.
- Gemini receives selected crops only. Full-page or full-document Gemini input requires the separate `allow_full_document_gemini` flag, which the public UI does not expose.
- The private acceptance book and its annotations are `EVALUATION_ONLY`; paths under `private_data/`, `data/ground_truth/`, `artifacts/`, and `jobs/` are ignored.
- Each page is an independent checkpoint. A failed page is recorded and processing continues.
- Canonical text is stored in logical Unicode order and is never reversed.

## Component map

```text
PDF/page images
  -> deterministic preprocessing
  -> LayoutProvider
  -> OcrProvider
  -> reading-order reconstruction
  -> deterministic boundary engine
  -> mixed-script run segmentation
  -> optional crop-only VisualAdjudicator
  -> CanonicalDocument checkpoint
  -> literal/polished DocumentRenderer
  -> structural, text, PDF, and visual validation
```

Provider protocols are defined in `src/arabic_schoolbook_ocr/protocols.py`:

- `OcrProvider.process_page(Image, PageContext) -> OcrPageResult`
- `LayoutProvider.analyze_page(Image) -> LayoutResult`
- `VisualAdjudicator.adjudicate(crop, candidates, context) -> AdjudicationResult`
- `DocumentRenderer.render_docx(CanonicalDocument, Path) -> RenderResult`

Implementations:

| Role | Local | Cloud | Test/research |
|---|---|---|---|
| OCR | `PaddleLocalOcrProvider` | `AzureDocumentIntelligenceProvider` | `MockOcrProvider`, `UnlimitedOcrProvider` preflight |
| Layout | `PaddleLocalLayoutProvider` | Azure layout returned with OCR | `MockLayoutProvider` |
| Adjudication | `DisabledAdjudicator` | `GeminiAdjudicator` (crops only) | `MockAdjudicator` |
| Render | `DocxDocumentRenderer` | n/a | n/a |

## Canonical invariants

Every text block contains `literal_text`, `unicode_normalized_text`, and `approved_corrected_text`. Normalization is a separate reversible/auditable transformation. Content corrections are never silently written into literal output. Unknown blocks remain present as `UNKNOWN`.

The boundary engine emits one of: `CONTINUE_WITH_SPACE`, `CONTINUE_WITHOUT_SPACE`, `SOFT_LINE_BREAK`, `NEW_PARAGRAPH`, `BLANK_PARAGRAPH_SPACE`, `LIST_ITEM_BOUNDARY`, `TABLE_CELL_BOUNDARY`, `PAGE_BREAK`, or `SECTION_BREAK`.

## Persistence

Each run uses a private job directory:

```text
jobs/<job_id>/
  run_manifest.json
  source/
  pages/<page>/source.png
  pages/<page>/preprocessed.png
  pages/<page>/layout.json
  pages/<page>/ocr.json
  pages/<page>/canonical.json
  pages/<page>/error.json
  document/canonical_document.json
  output/
```

Writes use a temporary sibling plus atomic replace. A resume operation trusts only complete JSON checkpoints.

## Current provider revisions

- Azure Document Intelligence Python SDK 1.0.x, service API `2024-11-30`, model `prebuilt-layout`.
- PaddleOCR 3.x / PP-StructureV3; Arabic recognition explicitly selects `lang="ar"` and `ocr_version="PP-OCRv3"` because current PP-OCRv5 language support does not include Arabic.
- Google GenAI SDK Interactions API; default model is configurable (`GEMINI_MODEL`) and currently `gemini-3.6-flash`.
- Unlimited-OCR upstream commit and weight revision are recorded in `MODEL_SUPPORT.md`; official BF16 loading is blocked below 8 GB VRAM and is therefore blocked on the current 6 GB GPU.

## Training boundary

There is no training command, trainer dependency, or path from the UI to a training operation. Future training work requires a new authorization and a legal-data review.
