# Data manifest and layer policy

No dataset payload is currently present. This file defines the only allowed storage and provenance scheme.

## Layer registry

| Layer | Storage root | Current status | Admitted source |
|---|---|---|---|
| A. General Arabic text corpus | `datasets/layer_a_general_text/` | Empty; candidate approved after user gate | Arabic E-Book Corpus v1 |
| B. Synthetic Arabic OCR pages | `datasets/layer_b_synthetic_ocr/` | Empty | Locally generated CC BY source pages after asset audit; external datasets held |
| C. Real historical Arabic print | `datasets/layer_c_historical_print/` | Empty/blocked | None |
| D. Modern Arabic schoolbook pages | `datasets/layer_d_modern_schoolbooks/` | Empty | None training-allowed |
| E. Private held-out acceptance books | `private_data/` | One locked book | Supplied PDF, acceptance only |

Dataset payload roots are ignored by Git. Version manifests and audit decisions live in `data_registry/`.

## Versioned directory convention

```text
datasets/
  layer_a_general_text/
    arabic_ebook_corpus/
      doi-10.5878-7rbh-gy93-v1/
  layer_b_synthetic_ocr/
    locally_rendered_arabic_ebook/
      recipe-<git-or-manifest-hash>/
    arabic_img2md/
      hf-b259f4e285483107f1585960cfd62e17bdc6c712/  # blocked
    sard/
      hf-1d09bbb8d40645b058118991cf92621a4d606197/  # blocked
  layer_c_historical_print/
    openiti_arabic_print_data/
      git-0e7ded8820602afa74899d9893504aa70ba2f7e2/  # blocked
  layer_d_modern_schoolbooks/
    <permissioned-book-family>/<manifest-version>/
```

No `latest/` aliases are allowed in a locked experiment.

## Canonical sample identity

```json
{
  "sample_id": "stable-content-derived-id",
  "source_dataset_id": "arabic-ebook-corpus",
  "source_revision": "doi:10.5878/7rbh-gy93#version-1",
  "source_item_id": "corpus-book-id",
  "source_book_family_id": "normalized-edition-family",
  "source_span_sha256": "",
  "source_url_or_doi": "https://doi.org/10.5878/7rbh-gy93",
  "source_license": "CC-BY-4.0",
  "rights_snapshot_id": "data-licenses-20260722",
  "derivation_recipe_id": "",
  "asset_license_ids": [],
  "split": "train_public_text",
  "task": "full_page_exact_transcription",
  "image_sha256": "",
  "target_sha256": ""
}
```

## Admission invariants

- `EVALUATION_ONLY` records cannot be exported to a training or validation loader.
- Every page, crop, line, and word retains the parent `source_item_id` and `source_book_family_id`.
- A family belongs to exactly one split across all derived tasks.
- Raw text, rendered pages, crops, annotations, and corrections receive separate immutable manifests.
- A license decision applies only to its exact revision; upstream updates require a new audit.
- Combining source-specific datasets or adapters requires a written compatibility decision.
