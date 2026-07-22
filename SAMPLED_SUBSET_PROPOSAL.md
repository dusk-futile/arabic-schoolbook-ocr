# Proposed sampled subset

This is a design only. No external dataset rows or model weights have been downloaded.

## Stage 1: currently eligible source

### Arabic E-Book Corpus v1

- Select **175 complete books**, approximately 10% of the 1,745-book corpus.
- Target approximately **8.15 million words** for tokenizer analysis.
- Use a deterministic seed: `20260722`.
- Stratify by primary genre, translation status, original language, publication decade, diacritic density, length decile, and presence of Latin/digit runs.
- Keep all text from one book in exactly one split.
- Preserve corpus metadata and add the DOI/version to every derived example.

After the font and template licenses are separately audited, generate **5,000 synthetic page pairs** from these source books. Proposed overlapping coverage quotas:

| Page characteristic | Minimum pages |
|---|---:|
| Plain one-column body text | 1,200 |
| Headings and section hierarchy | 700 |
| Questions, numbered lists, and bullets | 700 |
| Mixed Arabic-English runs | 600 |
| Tables or aligned key-value structures | 400 |
| Dense or two-column layouts | 500 |
| Diacritized prose/poetry | 500 |
| Digits, punctuation, citations, and footnotes | 400 |

Each rendered page must retain the complete source-book identity, source span checksum, template version, font file checksum/license, render seed, and target Markdown/JSON.

## Stage 2: conditional sources

These samples must not be materialized until their blockers are cleared.

### Arabic-Img2MD conditional sample

- Target: **2,000 pages**.
- Require at least **200 independently identified source books**, maximum 10 pages per book.
- Balance by target length, Markdown structure, diacritic density, mixed English, figures/tables, and page density.
- Stream only the canonical Parquet files; never clone the 178 GB repository representation.
- Do not trust the published train/test split until duplicate and source-book leakage checks pass.
- Current authorized count: **0**.

### SARD conditional sample

- Target: **6,000 pages**, exactly 1,000 from each declared font split: Amiri, Sakkal Majalla, Arial, Calibri, Scheherazade New, and Traditional Arabic.
- Use Hugging Face streaming with a deterministic bounded reservoir; do not download split CSV collections wholesale.
- Group by normalized `article_link`; all pages from the same article remain in one split.
- Balance text length deciles, topical category, digits, punctuation, diacritics, and article source.
- Verify that fonts themselves permit the intended use; a dataset license does not license third-party fonts.
- Current authorized count: **0** because commercial use, derivatives, and redistribution are blocked.

### OpenITI conditional sample

- Current authorized count: **0**.
- If exact rights are later confirmed, begin with no more than **300 image/XML pairs**, grouped by complete printed edition and balanced by typeface, print date, scan quality, and layout.
- Historical data must train a separate source-specific adapter first.

## Private target-domain data

- Supplied book: five representative pages used for local baseline only.
- Training sample count: **0**.
- Validation sample count: **0**.
- Acceptance sample count: **209 pages in one locked book**.

## Sampling acceptance checks

Before any sample is admitted:

1. License decision is `APPROVED` for the exact revision.
2. Source item identity and checksum are non-empty.
3. Book/article/edition family is assigned to one split only.
4. Perceptual image hash and normalized text hash show no cross-split duplicate.
5. Font, template, illustration, and icon licenses are recorded for synthetic pages.
6. The dataset version directory is immutable after its manifest hash is locked.
