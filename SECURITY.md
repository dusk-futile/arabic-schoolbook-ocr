# Security policy

## Supported version

Security fixes target the current `main` branch and latest tagged release.

## Reporting a vulnerability

Do not open a public issue containing secrets, private document content, path traversal details with live files, or exploitable provider credentials. Use the repository host's private security-advisory channel. Include the affected version, reproduction steps using synthetic data, impact, and a proposed mitigation if known.

## Security boundaries

- Local mode must not make provider network requests.
- Azure and Gemini require both configured credentials and explicit per-job consent.
- Gemini crop verification and selected full-page formatting/QA have distinct consent scopes; every capability is disabled by default.
- Uploaded filenames are reduced to a basename, job identifiers are restricted, and file-serving paths must remain inside the job directory.
- Job responses use `Cache-Control: no-store`; secrets are neither logged nor stored in manifests.
- Training is disabled and private acceptance data is ignored by version control.

Deploy behind an authenticated reverse proxy when binding beyond loopback. Terminate TLS, set request-size/time limits, isolate the job volume, run as a non-root user, and use a dedicated secret store. The built-in server is not a multi-tenant authorization system.

## Dependency and input risk

PDFs, images, OCR model files, and office documents are untrusted inputs. Keep Ghostscript/Poppler, Pillow, FastAPI, Paddle, and the office renderer patched. Run conversions in a low-privilege container or account. CI performs static checks, dependency audits, and secret scanning, but these do not replace operational monitoring.
