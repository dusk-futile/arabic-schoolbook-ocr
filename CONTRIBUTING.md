# Contributing

## Before opening a change

Use synthetic, public-domain, or clearly licensed fixtures. Never submit private books, page crops, OCR derivatives, API keys, proprietary fonts, external dataset payloads, or model weights. Record exact source revision and license for every new third-party asset.

Create a focused branch, explain behavior and privacy impact, and add tests for changed invariants. Provider changes must preserve cloud fail-closed behavior and the canonical schema. Content corrections must remain human-gated; literal text must remain immutable evidence.

## Development checks

```powershell
python -m pip install -e ".[dev]"
python -m ruff check .
python -m mypy src
python -m pytest
cd web
pnpm install --frozen-lockfile
pnpm lint
pnpm build
```

For local Paddle integration, install `.[local,dev]`. Mock tests must pass without downloading models or contacting a network. Regenerate the CC0 fixture with `python scripts/create_demo_fixture.py` and confirm both DOCX validation reports pass.

## Pull-request checklist

- tests and documentation updated;
- no secret or private artifact in the diff;
- no network call without explicit consent;
- new dependency license recorded in third-party notices;
- data/model code and license terms distinguished;
- user-visible limitations and migration notes documented.
