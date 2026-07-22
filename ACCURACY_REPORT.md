# Accuracy report

Report date: 2026-07-22
Status: `BLOCKED_PENDING_HUMAN_GROUND_TRUTH`

No CER, WER, structural-accuracy, or provider-improvement percentage is reported. The locked 30-page evaluation set contains 30 OCR-seeded drafts, **0 human-reviewed pages**, and **0 human-approved pages**. Model agreement and the PDF's corrupted embedded text are not ground truth.

| Required measure | Local baseline | Gemini variants | Reason no number is shown |
|---|---:|---:|---|
| Character error rate | `NOT_MEASURED` | `NOT_RUN` | Human reference text is incomplete |
| Word error rate | `NOT_MEASURED` | `NOT_RUN` | Human reference text is incomplete |
| Digits / English tokens / punctuation | `NOT_MEASURED` | `NOT_RUN` | Protected-token references are incomplete |
| Heading / paragraph-boundary F1 | `NOT_MEASURED` | `NOT_RUN` | Human block types and boundaries are incomplete |
| Reading-order / table accuracy | `NOT_MEASURED` | `NOT_RUN` | Human order and cell references are incomplete |
| Missing / hallucinated blocks | `NOT_MEASURED` | `NOT_RUN` | Requires pixel-to-reference human adjudication |
| Unresolved rate | 1,457 / 1,469 (99.18%) | `NOT_RUN` | This is workflow state, not transcription accuracy |

The local full-book run completed 209/209 pages without page failures and produced structurally valid literal and polished DOCX files. That establishes artifact integrity only. The ten-page visual formatting audit is `NEEDS_CORRECTION`: reconstructed content is top-compressed and source-relative table/figure spacing is not yet faithful.

Publication gates for actual accuracy results:

1. A human corrects and approves all 30 locked pages, including text, digits, boxes, types, reading order, paragraph boundaries, runs, and table cells.
2. Each provider mode runs on exactly those pages with its revision, settings, latency, token/API usage, and estimated cost recorded.
3. The evaluator refuses any page whose `human_reviewed` and approval fields are not true.
4. Results include paired per-page deltas and confidence intervals; no model output is used as its own reference.

The private ground-truth draft remains `EVALUATION_ONLY`, `training_allowed=false`, and is ignored by version control. See [GROUND_TRUTH.md](GROUND_TRUTH.md), [BASELINE_RESULTS.md](BASELINE_RESULTS.md), and [UNRESOLVED_BLOCK_ANALYSIS.md](UNRESOLVED_BLOCK_ANALYSIS.md).
