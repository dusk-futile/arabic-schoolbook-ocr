# Dataset comparison

| Resource | Layer | Modality and scale | Best use | Domain fit | Provenance quality | License status | Initial action |
|---|---|---|---|---|---|---|---|
| Arabic E-Book Corpus v1 | A - General Arabic text | 1,745 books; about 81.5M words; HTML/plain text | Tokenizer audit; source text for newly rendered synthetic pages | Medium: modern book language, not schoolbook layout | Good dataset-level metadata; preserve each book's identity | CC BY 4.0, green | Propose 175-book, book-stratified sample after approval |
| Arabic-Img2MD | B - Synthetic Arabic OCR pages | 15,216 image/Markdown pairs; 13,694 train and 1,522 test | Arabic OCR/Markdown baseline and page-structure pretraining | Medium: standard book pages; Hindawi-biased | Weak: paper says Hindawi scrape, but card lacks per-work license/identity | GPL-3.0 card; source rights unresolved | Zero training samples until clarified |
| SARD | B - Synthetic Arabic OCR pages | 2,621,075 A4-style images; six font splits; 1.54 TB | Font/transcription pretraining | Low-to-medium: clean, fixed synthetic book layouts with no scan defects | Article links and sample IDs exist, but card/count inconsistencies remain | CC BY-NC-ND plus no-redistribution source note | No download/training; retain a conditional 6,000-page sampling design |
| OpenITI Arabic Print Data | C - Real historical Arabic print | 4,693 image/XML pairs; about 7.47 GB Git blobs | Historical print transcription and layout | Low for modern schoolbooks; useful robustness layer | Repository organizes typefaces/layouts but lacks per-image rights in README | Exact repository unlicensed | Zero samples until exact rights are confirmed |
| Supplied private book | E - Private held-out acceptance | 209-page born-digital PDF; 3.23 MB | Acceptance testing and error taxonomy | Primary target evidence supplied in this task; university lecture-book style | Exact file hash and local manifest recorded | `EVALUATION_ONLY` | Full local acceptance baseline complete; no training/validation |
| Future permissioned schoolbooks | D - Modern Arabic schoolbook pages | None admitted | Target-domain training/validation/test | Highest | Must be one manifest per complete book/edition family | Not yet licensed | Empty layer until the user marks specific books training-allowed |

## Quality notes

- Arabic E-Book Corpus is text-only. It must never be reported as aligned OCR data.
- Synthetic pages from the Arabic E-Book Corpus must use independently audited fonts, icons, images, and templates.
- Arabic-Img2MD's published test split is not automatically leakage-safe because source-book identity is not present in the card.
- SARD is clean synthetic typography and explicitly lacks scan artifacts, blur, or distortion. It cannot substitute for modern schoolbook scans.
- OpenITI is a historical/generalization layer, not a target-domain substitute.
- With only one private book, book-level modern-domain train/validation/test metrics cannot yet be constructed without violating the acceptance holdout.

## Current admissible layers

| Layer | Status | Contents now |
|---|---|---|
| A. General Arabic text corpus | Candidate approved after report approval | Arabic E-Book Corpus v1 only |
| B. Synthetic Arabic OCR pages | Empty | Generate locally from Layer A after font/template audit; external datasets held |
| C. Real historical Arabic print | Empty | OpenITI blocked |
| D. Modern Arabic schoolbook pages | Empty | No training-allowed books supplied |
| E. Private held-out acceptance books | Locked | One supplied PDF, 209 pages, SHA-256 prefix `d2a34a23` |
