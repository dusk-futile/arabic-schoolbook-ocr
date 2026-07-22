# Data and model license register

Audit date: 2026-07-22. This is an engineering compliance screen, not legal advice. "Commercial" and "redistribution" below describe the declared license and any source terms found; unresolved provenance overrides a permissive top-level label.

## Decision summary

| Resource or component | Exact revision | Declared license | Commercial use | Redistribution | Attribution / share-alike | Training decision |
|---|---|---|---|---|---|---|
| Arabic-Nougat repository code | [`9c0b9a6`](https://github.com/mohamedalirashad/arabic-nougat/tree/9c0b9a6d51bac6381f5129e5a92b720f6aaf4ab5) | README says CC BY-SA 4.0; repository has no `LICENSE` file and GitHub detects none | Stated license permits it | Stated license permits it | Attribution, change notice, same-license adaptations | **HOLD** - obtain a standalone license confirmation before relying on the code license |
| Arabic-Img2MD dataset | [`b259f4e`](https://huggingface.co/datasets/MohamedRashad/arabic-img2md/tree/b259f4e285483107f1585960cfd62e17bdc6c712) | GPL-3.0 on dataset card | GPL permits commercial use in principle | GPL permits distribution under its conditions | GPL copy/source obligations; application to data/model outputs needs review | **HOLD** - scraped-source provenance is insufficient |
| Arabic Base Nougat weights | [`c651f8c`](https://huggingface.co/MohamedRashad/arabic-base-nougat/tree/c651f8cb5c123935c73970db105c8e40587805ef) | GPL-3.0 | Yes in principle | Yes under GPL conditions | Model card requests license copy and acknowledgment | Internal evaluation only pending training-data review; no public derivative |
| Arabic Large Nougat weights | [`23ad1d7`](https://huggingface.co/MohamedRashad/arabic-large-nougat/tree/23ad1d7c934436f4d34417131051ddb3089b37e8) | GPL-3.0 | Yes in principle | Yes under GPL conditions | Model card requests license copy and acknowledgment | Internal evaluation only pending training-data review; no public derivative |
| SARD | [`1d09bbb`](https://huggingface.co/datasets/riotu-lab/SARD/tree/1d09bbb8d40645b058118991cf92621a4d606197) | CC BY-NC-ND 4.0 plus stricter source-use note | **No** | Source note says **no redistribution or republication** without permission | Attribution required; no distributed adaptations | **BLOCKED** for training and public/commercial model release |
| Arabic E-Book Corpus | DOI [`10.5878/7rbh-gy93`](https://doi.org/10.5878/7rbh-gy93), Version 1, published 2024-12-11 | CC BY 4.0 | Yes | Yes | Attribution and change indication; no share-alike | **APPROVED CANDIDATE** for Layer A and synthetic text generation |
| OpenITI Arabic Print Data | [`0e7ded8`](https://github.com/OpenITI/arabic_print_data/tree/0e7ded8820602afa74899d9893504aa70ba2f7e2) | No license in exact repository | Unknown / not granted | Unknown / not granted | Unknown | **BLOCKED** until repository and per-image/XML licensing are confirmed |
| Supplied private book | SHA-256 `d2a34a23cf247382af5990b30b3fe2cf8c19878feb7da6e1fdf2c4343c94f7d2` | User permission state, not a public license | Not assessed | No | N/A | `EVALUATION_ONLY`; never training or validation |
| Unlimited-OCR repository code | [`1ab6b46`](https://github.com/baidu/Unlimited-OCR/tree/1ab6b46b989ebf26328a968d87ce583a9650ab90) | MIT | Yes | Yes | Preserve copyright/license notice | Approved for code use, subject to dependency audit |
| Unlimited-OCR weights | [`2a06ebf`](https://huggingface.co/baidu/Unlimited-OCR/tree/2a06ebf2d6f600f95fd2b99f6ccdee18a52e3b8f) | MIT on model card | Yes | Yes | Preserve notice | Approved for local baseline when compatible hardware is available |
| PaddleOCR/PaddleX code packages | PaddleOCR 3.7.0, PaddleX 3.7.2 | Apache-2.0 | Yes | Yes | Preserve copyright/license notices | Approved application dependencies; not a data license |
| Paddle local model artifacts | Layout `aa52b852...`; detector `58f4e5b1...`; Arabic recognizer `2feba5ee...` | Apache-2.0 on each exact cached model card | Yes | Yes under Apache-2.0 | Preserve license/notices and mark changes | Approved for local inference and bundling under license; not treated as training data |
| Project-authored synthetic demo | Repository version 0.1.0 | CC0 1.0 | Yes | Yes | None required | Public fixture only; not a training-corpus approval |

## Resource findings

### Arabic-Nougat, Arabic-Img2MD, and weights

- The repository at commit `9c0b9a6d51bac6381f5129e5a92b720f6aaf4ab5` contains eight files and no standalone license file. Its README links to [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), which permits commercial sharing and adaptation with attribution and share-alike.
- The [Arabic-Img2MD card](https://huggingface.co/datasets/MohamedRashad/arabic-img2md) declares GPL-3.0, 15,216 examples, and a canonical Parquet download of about 2.94 GB. The Hugging Face repository also retains roughly 178 GB of Arrow/data material; cloning the repository is not an acceptable initial access method.
- The [paper](https://arxiv.org/pdf/2411.17835) says the paired pages were generated from HTML scraped from the Hindawi website. Neither the paper nor dataset card supplies per-book identifiers, per-work license snapshots, or evidence that only unrestricted Hindawi works were selected.
- A GPL label on the compiled dataset does not cure rights missing from source works. Training and public redistribution therefore remain on hold until the source selection and licenses are documented.
- The base and large model cards independently label their weights GPL-3.0. Their training-data provenance inherits the unresolved Arabic-Img2MD concern.

### SARD

- The [dataset card](https://huggingface.co/datasets/riotu-lab/SARD) declares CC BY-NC-ND 4.0 and 1.54 TB for 2,621,075 synthetic document images.
- The card identifies Alukah article text as the source and states that use is limited to non-commercial purposes; redistribution, republication, or commercial use is not permitted without permission and attribution.
- CC BY-NC-ND does not permit distributing adapted material. Whether trained weights are an adaptation is legally unsettled, so the conservative decision is to block training rather than risk an incompatible public or commercial model.
- The card is internally inconsistent: it says five fonts but lists six splits, and a linked collection reports a different image count. Any future approved sample needs its own count and checksum validation.

### Arabic E-Book Corpus

- The exact user-specified record is [Version 1 at the Swedish National Data Service](https://researchdata.se/en/catalogue/dataset/2024-145), DOI `10.5878/7rbh-gy93`, published 2024-12-11.
- It contains 1,745 Hindawi books and approximately 81.5 million words in HTML and plain-text forms. The repository record lists five files totaling 420.42 MiB.
- The record and README declare [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Commercial use, redistribution, and adaptation are allowed with attribution and change indication.
- The accompanying article states that only freely licensed books were included. Even so, every selected book must retain its title, author, translator, source identifier, and corpus-version identity in generated examples.
- A newer Sprakbanken mirror and a Hugging Face copy exist, but they are not the audited revision for this decision.

### OpenITI Arabic Print Data

- The exact repository commit contains 9,387 files and about 7.47 GB of Git blobs: 4,693 ALTO XML files paired with 4,693 images (PNG/JPG/TIF), plus a README.
- The exact repository has no license file and GitHub detects no license. Its one-paragraph README does not identify per-book image providers or rights.
- General [OpenITI documentation](https://openiti.org/documentation/) describes corpus releases as CC BY-NC-SA 4.0, while newer platform terms distinguish OpenITI material from third-party material. Those statements do not unambiguously license this 2022 image/XML repository or its individual scan images.
- Per the user's instruction, this resource stays blocked until OpenITI confirms the exact repository license and image-level rights.

### Supplied book

- Permission defaults to `EVALUATION_ONLY`.
- `training_allowed: false`, `public_redistribution_allowed: false`, and `external_api_allowed: false`.
- The book and all page images, OCR output, and annotations remain in ignored local directories.

## Required attribution records

Every admitted sample must carry:

```text
source_dataset_id
source_revision
source_item_id
source_title
source_creator
source_url_or_doi
source_license_spdx_or_url
source_license_snapshot_id
source_checksum
derivation_recipe_id
synthetic_font_license_ids
split_book_family_id
```

No record with an empty source identity may enter training.
