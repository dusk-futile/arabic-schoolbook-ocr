# Third-party notices

Audit date: 2026-07-22. No third-party dataset payload, private page, model weight, or external source code is vendored in this repository. Python/JavaScript packages and model artifacts are resolved by the installer/provider and retain their own notices.

## Runtime libraries

| Component | Declared license | Use |
|---|---|---|
| FastAPI, Starlette, Uvicorn, Pydantic | MIT / BSD-family as declared by each package | API, validation, server |
| Pillow | HPND | Image handling |
| python-docx | MIT | Editable DOCX generation |
| pypdf | BSD-3-Clause | PDF inventory/page count |
| PaddlePaddle, PaddleOCR, PaddleX | Apache-2.0 code packages | Local OCR/layout runtime |
| Azure AI Document Intelligence SDK | MIT | Optional cloud provider |
| Google GenAI SDK | Apache-2.0 | Optional selective adjudicator |
| React, React DOM | MIT | Web interface |
| Vite | MIT | Frontend build |
| Lucide React | ISC | Interface icons |
| arabic-reshaper | MIT | Public fixture generation only |
| python-bidi | LGPL-3.0-or-later | Public fixture generation only |

Transitive dependencies have their own licenses. Release builds must retain package metadata and pass dependency review; this summary is not a replacement for included license files.

## Model artifacts

Paddle model files are downloaded to the user's cache only after Local mode is selected. Tested cache identities are:

- `PP-DocLayout_plus-L` revision `aa52b8528c84f9b1a34ac3a88fe0e576edb9d11d`;
- `PP-OCRv3_mobile_det` revision `58f4e5b132e34e516486fb0d0266c662feb48ca1`;
- Arabic PP-OCRv3 recognition revision `2feba5ee71822bb7ee0bbecf134e62f8ec9f368a`.

Each exact cached model card declares Apache-2.0. Preserve its license/notices and mark modifications when redistributing an offline bundle. This weight license does not automatically license model training data for reuse.

Optional Unlimited-OCR repository code commit `1ab6b46b989ebf26328a968d87ce583a9650ab90` and weights revision `2a06ebf2d6f600f95fd2b99f6ccdee18a52e3b8f` declare MIT. Neither is vendored; weight provenance and dependencies still require release review.

## System tools

PDF rendering may invoke a user-installed Ghostscript or Poppler executable. DOCX-to-PDF validation may invoke LibreOffice. These executables are not copied into the Python wheel. The provided container installs Poppler and LibreOffice from Debian packages and must preserve their applicable notices/source-offer obligations. Ghostscript has AGPL/commercial licensing considerations and is not bundled by this repository.

Windows.Media.Ocr is an optional operating-system component used only on Windows.

## Data and public assets

The original synthetic page, illustration, canonical JSON, and DOCX files under `examples/demo/` are dedicated under CC0 1.0. Candidate external datasets and the private acceptance book are not distributed; their exact restrictions and decisions are in `DATA_LICENSES.md`.
