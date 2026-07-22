# Book-level train, validation, test, and acceptance split

## Current locked assignment

| Book family | Books | Pages | Rights state | Split | Training | Validation |
|---|---:|---:|---|---|---:|---:|
| `psychology-creativity-giftedness-d2a34a23` | 1 | 209 | `EVALUATION_ONLY` | `acceptance_private` | 0 | 0 |
| Modern training-allowed schoolbooks | 0 | 0 | None supplied | Unassigned | 0 | 0 |

The supplied book is the only target-domain book. Assigning any of its pages to training or validation would contaminate the only private acceptance book, so all 209 pages remain together in Layer E.

## Arabic E-Book source split for synthetic generation

For the proposed 175-book text sample:

| Split | Complete source books | Percent | Purpose |
|---|---:|---:|---|
| `train_public_text` | 123 | 70.3% | Tokenizer statistics and synthetic training pages |
| `validation_public_text` | 26 | 14.9% | Synthetic-pipeline/model selection only |
| `test_public_text` | 26 | 14.9% | Untouched public-text generalization test |
| `acceptance_private` | 1 separate supplied book | N/A | Target-domain acceptance only |

The 70/15/15 public-source split is intentionally separate from private acceptance. It avoids pretending that one private book can supply 10% of a statistically meaningful book collection.

## Future modern-schoolbook allocation

When at least ten permissioned, non-duplicate modern schoolbook families exist, use the following starting allocation:

| Split | Books per 10 | Permission requirement |
|---|---:|---|
| Train | 7 | Explicit training permission |
| Validation | 1 | Explicit validation/training permission |
| Internal held-out test | 1 | Evaluation permission; never train/tune |
| Private acceptance | 1 | Evaluation only; never train/tune |

For fewer than ten permissioned books, use book-level cross-validation among training-allowed books while keeping every acceptance book fixed and untouched.

## Family grouping rules

The atomic split unit is `book_family_id`, not a PDF and never a page. The same family includes:

- alternate scans of the same edition;
- PDF and image exports of the same edition;
- revised files with substantially copied page layouts;
- teacher/student variants with copied content where leakage is likely;
- adjacent editions flagged by ISBN, text similarity, or layout similarity.

## Locking procedure

1. Normalize identifiers and metadata.
2. Compute SHA-256, page perceptual hashes, and normalized text MinHash.
3. Cluster editions and near-duplicates into book families.
4. Stratify families by grade, subject, country, publisher, layout, and scan quality.
5. Assign complete families with seed `20260722`.
6. Write the family list and manifest hash before page rendering or annotation.
7. Reject any example whose source family disagrees with the locked split.

No current page-level split has been created for the private book.
