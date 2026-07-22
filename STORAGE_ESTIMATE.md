# Estimated storage requirements

Estimates use the audited upstream records as of 2026-07-22. Decimal GB/TB are used where the source uses them; GiB/MiB are shown for local filesystem values. Current free space on `C:` during the audit was approximately 121.3 GB.

| Resource | Full upstream footprint | Proposed initial local footprint | Notes |
|---|---:|---:|---|
| Arabic-Nougat code | About 0.27 MB in Git blobs | 0 MB now; under 5 MB if later cloned | No clone performed; code license still needs clarification |
| Arabic-Img2MD canonical Parquet | 2.94 GB download; about 3.01 GB dataset size | 0 now; conditional 2,000-row sample about 0.39 GB compressed and up to 1 GB working cache | The HF repository also exposes about 178 GB of Arrow/raw material. Never clone or download the whole repo for the initial sample |
| SARD | 1.54 TB | 0 now; conditional 6,000-row sample about 3.5 GB plus 10-20% index/cache overhead | Average implied stored row is about 0.588 MB. Full download is unjustified and exceeds local capacity |
| Arabic E-Book Corpus v1 | 420.42 MiB for five repository files | 100-180 MB expanded text for a 175-book/10% word sample; 1-3 GB for 5,000 generated PNG/JSON page pairs | Download only the required text/metadata files, not redundant formats |
| OpenITI Arabic Print Data | 7,474,332,842 Git-blob bytes (about 6.96 GiB); allow 8-10 GB with Git metadata/checkout | 0 | No download while exact image-data license is unconfirmed |
| Supplied PDF | 3,228,435 bytes (about 3.08 MiB) | Existing source plus 255.46 MiB of full-book page checkpoints/evidence | Measured after all 209 pages; private artifacts remain ignored |
| Unlimited-OCR BF16 weights/runtime | Approximately 6-7 GB of weights plus framework/cache overhead | 0 | Official recipe requires at least 8 GB VRAM; local GPU has 6 GB, so no weight download was justified |
| Local Paddle production models | 135.6 MiB across the three selected cached model directories | 135.6 MiB plus Python runtime | Exact revisions are recorded in `MODEL_SUPPORT.md` |
| Full private acceptance job | 303.75 MiB measured, 3,413 files | 255.46 MiB page evidence plus 15.87 MiB outputs; remaining bytes are source/document checkpoints | Private and ignored; includes 209-page OCR evidence and deliverables |
| Private 30-page ground-truth draft | 1.07 MiB measured, 2 files | No additional training storage | Private, ignored, unreviewed, and `training_allowed=false` |

## Proposed phase budgets

| Phase | Payload | Disk budget |
|---|---|---:|
| Audit and baseline (current) | Documents, five private page renders, Windows OCR JSON | Under 10 MB in workspace/private artifacts |
| Green-data tokenizer audit | Arabic E-Book metadata plus 175 complete-book texts | 0.25 GB ceiling |
| Green-data synthetic pilot | 5,000 page images, annotations, manifests, and QA thumbnails | 3 GB ceiling |
| Conditional Arabic-Img2MD sample | 2,000 canonical Parquet-streamed rows | 1 GB ceiling |
| Conditional SARD sample | 6,000 streamed rows, six fonts balanced | 5 GB ceiling |

The audit, five-page smoke, public demo, and full 209-page private acceptance phases have been executed. Green-data phases still require approval; conditional phases additionally require their license blockers to be cleared.

## Capacity conclusion

- A full SARD download is impossible on the current drive and is not justified.
- A full 178 GB Arabic-Img2MD repository clone would exceed free space and would duplicate data; use only canonical Parquet streaming if it is later approved.
- OpenITI is small enough technically but remains prohibited legally.
- Keep a minimum 25 GB safety margin for operating-system, package, and model-cache growth.
