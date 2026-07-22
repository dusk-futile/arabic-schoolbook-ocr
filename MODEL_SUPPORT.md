# Model and provider support

Audit date: 2026-07-22. Model artifacts are downloaded to local provider caches and are not vendored in this repository.

| Component | Tested/pinned version or revision | License status | Hardware/support state |
|---|---|---|---|
| PaddlePaddle CPU | 3.2.2 on Windows; `>=3.2.2,<3.3` on Linux | Apache-2.0 package | Tested on Windows CPU; 3.3.x excluded due observed oneDNN crash |
| PaddleOCR | 3.7.0 (`>=3.5,<4`) | Apache-2.0 code; model terms reviewed separately | Arabic explicitly uses PP-OCRv3 multilingual recognizer |
| PaddleX | 3.7.2 | Apache-2.0 code; model terms reviewed separately | Direct layout-model API, not the full PP-Structure mega-pipeline |
| PP-DocLayout_plus-L | `aa52b8528c84f9b1a34ac3a88fe0e576edb9d11d` | Apache-2.0 on exact cached model card | Tested on CPU; largest local component |
| PP-OCRv3_mobile_det | `58f4e5b132e34e516486fb0d0266c662feb48ca1` | Apache-2.0 on exact cached model card | Tested on CPU |
| Arabic PP-OCRv3 mobile recognition | `2feba5ee71822bb7ee0bbecf134e62f8ec9f368a` | Apache-2.0 on exact cached model card | Tested on CPU |
| Azure Document Intelligence | SDK `>=1.0.2,<2`, service `2024-11-30`, `prebuilt-layout` | Commercial service terms | Implemented, not run on private book without opt-in |
| Gemini adjudicator | Google GenAI SDK `>=1,<2`, model configured by `GEMINI_MODEL` | Commercial service/model terms | Selective disputed crops only; structured output; full book disabled |
| Unlimited-OCR code | commit `1ab6b46b989ebf26328a968d87ce583a9650ab90` | MIT | Optional research provider |
| Unlimited-OCR weights | revision `2a06ebf2d6f600f95fd2b99f6ccdee18a52e3b8f` | MIT on model card | Official BF16 path blocked on current 6 GB GPU; >=8 GB required by official recipe |

## Local selection rationale

Current Paddle PP-OCRv5 language support does not provide the required Arabic recognizer, so the provider explicitly selects `lang="ar"` and `ocr_version="PP-OCRv3"`. Layout uses `PP-DocLayout_plus-L`. CPU inference disables MKL-DNN in provider configuration on the tested Windows stack for stability.

Windows.Media.Ocr is an independent verifier on Windows and supplies no confidence scores. Linux containers omit it and use Paddle alone unless another verifier is configured.

## Unlimited-OCR policy

Environment/hardware preflight runs before loading weights. Official BF16 inference is refused below 8 GB VRAM. Quantization is labeled experimental until an exact revision, quantizer, calibration method, quality benchmark, license review, and memory profile are recorded. A future remote endpoint requires explicit private-data transfer approval and must not change the UI or canonical schema.

The current remote setting is a fail-closed transport stub, not a working network client; configuring an endpoint does not mark the provider available or transmit data.

## Reproducibility

Every acceptance run records package versions, provider names, source SHA-256, model-cache revisions, consent, device, and platform in `run_manifest.json`. Cache revisions above were read from local model metadata; revalidate them after any provider upgrade.
