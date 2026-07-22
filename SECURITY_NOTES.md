# Security and privacy notes

- The supplied book and derived pages stay in ignored local paths.
- `external_api_allowed: false`; no book/page was uploaded.
- Dataset payloads, model weights, checkpoints, adapters, secrets, and raw artifacts are ignored by Git.
- The baseline used local PDF parsing, local Ghostscript rendering, and the installed Windows OCR engine.
- Filenames are not used as trusted identifiers; the book is keyed by SHA-256.
- Upload handlers validate PDF signatures, reduce filenames to basenames, enforce size/page confirmation limits, contain file paths, set no-store responses, and bind to `127.0.0.1` in documented local commands.
- Training endpoints must remain disabled until a manifest passes rights, split, and duplicate checks.
- Logs must store hashes/IDs by default, not full private text.
- Any cloud proposal must name the provider, region, transmitted data, retention policy, credentials path, cost, and deletion procedure before approval.
- Local dependency audit on 2026-07-22: `pip-audit` found no known vulnerabilities after upgrading pip/pytest; `pnpm audit --audit-level=high` found none. CI reruns both checks.
- Docker definitions were statically parsed but not built on this workstation because Docker is not installed; CI owns the container build gate.
