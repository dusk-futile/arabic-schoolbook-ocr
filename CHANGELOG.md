# Changelog

All notable changes follow a Keep a Changelog style. The project uses semantic versioning once releases are tagged.

## 0.1.0-alpha - 2026-07-22

### Added

- local Paddle Arabic OCR and layout providers, Windows verifier, Azure provider, selective Gemini adjudicator, mocks, and Unlimited-OCR preflight;
- canonical block, boundary, table, mixed-script, consent, usage, and correction schemas;
- per-page preprocessing, reading order, checkpointing, failure continuation, overlays, reports, and full-book runner;
- semantic RTL/LTR literal and polished DOCX exports with real lists, tables, figures, headers, footers, and validation;
- FastAPI backend and a minimalist one-page React flow for PDF upload, real processing progress, and direct polished-Word download;
- public CC0 Arabic demonstration fixture, tests, licensing records, privacy/security documentation, container files, and CI;
- 30-page private benchmark selection with ground-truth metrics blocked until human approval.
- completed 209-page local acceptance output with checkpoint resume, exact PDF page-count verification, and source-scale figure rendering.
- three optional, consent-gated Gemini roles for crop verification, structural formatting, and rendered-Word visual QA;
- process-local Settings UI with non-echoed keys, independent flags, strict schemas, bounded retries/concurrency, and usage/cost evidence;
- cross-platform CLI, Windows launcher/ZIP workflow, synthetic smoke test, and alpha GHCR workflow;
- unresolved-block analysis, ten-page formatting audit, and machine-readable accuracy-status report.

### Security

- cloud calls fail closed without job-scoped opt-in;
- full-page Gemini calls require a second explicit consent scope and remain disabled by default;
- private paths and credentials excluded from version control.

### Known limitation

- measured accuracy is pending human-corrected ground truth; no training has been run.
- the optional AI layer has contract tests but no real private-page run; the Word formatting audit remains `NEEDS_CORRECTION`.
