# Unresolved-block analysis

Run analyzed: `book-local-acceptance-20260722`
Analysis date: 2026-07-22
Classification: private `EVALUATION_ONLY`

This report analyzes the canonical JSON produced by the 209-page local acceptance run. It does not lower a confidence threshold, reinterpret an unresolved block as correct, or use the private book for training.

## Executive finding

`unresolved` primarily means **verification was required but no enabled visual adjudicator resolved it**. It does not mean that 1,457 blocks are empty, nor does it mean that every block has low primary-OCR confidence.

The pipeline compared Paddle OCR with Windows OCR. It sent 1,457 of 1,469 blocks through the adjudication branch:

| Trigger | Blocks |
|---|---:|
| Paddle/Windows normalized text disagreement | 1,428 |
| Low Paddle confidence without a text disagreement | 29 |
| **Total requiring adjudication** | **1,457** |

Gemini was disabled and no private crop was uploaded. The disabled adjudicator deliberately returned `unresolved=true` for all 1,457 triggered blocks. Twelve blocks did not trigger adjudication and remained resolved under the local pipeline rules.

This is fail-closed behavior. The high unresolved count exposes missing verification rather than hiding it.

## Thresholds and confidence data

Two thresholds existed in the completed run:

- Canonicalization initially marked a block unresolved when Paddle confidence was below `0.70` or its type was `UNKNOWN`.
- The verifier/adjudicator branch was triggered when Paddle confidence was below `0.72` **or** Paddle and Windows text disagreed.

Confidence distribution:

| Paddle confidence | All blocks | Unresolved blocks |
|---|---:|---:|
| Below 0.70 | 167 | 167 |
| 0.70–0.719 | 16 | 16 |
| 0.72–0.849 | 206 | 204 |
| 0.85 or higher | 1,080 | 1,070 |
| **Total** | **1,469** | **1,457** |

No canonical block is missing a numeric confidence. However, Windows OCR does not expose a calibrated confidence through the current adapter: 1,424 secondary candidates carry the adapter's neutral `0.5` value. This value is evidence of unavailable native confidence, not a measured 50% probability.

The result must not be “fixed” by lowering either threshold. Most unresolved blocks are caused by cross-provider disagreement, including 1,070 high-confidence Paddle blocks.

## Text and empty blocks

| Content state | All blocks | Unresolved blocks |
|---|---:|---:|
| Non-empty extracted text | 1,453 | 1,442 |
| Empty text | 16 | 15 |
| **Total** | **1,469** | **1,457** |

Empty blocks are expected for some figures and structural regions. An empty figure transcription is not an OCR page failure.

## Unresolved blocks by type

| Block type | Count |
|---|---:|
| Body paragraph | 1,029 |
| Document title | 4 |
| Heading level 2 | 190 |
| Heading level 3 | 21 |
| Question | 25 |
| Caption | 4 |
| Table | 2 |
| Figure | 9 |
| Page number | 163 |
| Unknown | 10 |
| **Total** | **1,457** |

Aggregating the requested major categories gives 1,029 paragraphs, 215 titles/headings, 2 tables, 4 captions, and 9 figures. The remaining 198 blocks are questions, page numbers, and unknown regions.

## Reversed Arabic word order

Without human ground truth, the exact number of blocks whose final transcription has reversed Arabic word order is **not determinable**. The two OCR systems are candidates, not reference truth.

A conservative automated proxy found:

- 7 blocks where the token sequence from one provider is the exact reverse of the other provider's sequence;
- 8 blocks total where both providers contain the same token multiset but use a different order.

These are confirmed provider-order conflicts, not proof that a particular candidate is correct. The earlier five-page Windows baseline also demonstrated systematic right-to-left word-order reversal, so every Windows candidate must remain geometric evidence rather than ground truth.

## Suspected hallucinations

No hallucination can be confirmed without comparison to the page pixels or approved ground truth.

For review prioritization, a deliberately broad **severe-divergence proxy** flags 807 unresolved non-figure/table blocks when either:

- one matched provider candidate is empty and the other is not; or
- both are non-empty but their normalized character-sequence similarity is below 0.25.

This count must not be reported as 807 hallucinations. Arabic word-order reversal, missing spaces, line grouping, block-boundary differences, and verifier truncation can all produce the same signal. The 807 blocks are “possible omission/hallucination or segmentation conflicts requiring visual review.” Confirmed hallucinations remain `NOT_MEASURED`.

## What the unresolved flag does and does not mean

It can mean:

- Paddle and Windows returned different text for the same geometric region;
- Paddle confidence was below 0.72;
- a required visual verification agent was disabled;
- verification failed and the primary candidate was retained fail-closed.

It does not by itself mean:

- the block has no text;
- the primary OCR is wrong;
- the secondary OCR is right;
- confidence is below 0.85;
- a hallucination occurred;
- a machine correction is approved for polished output.

## Required remediation

1. Preserve all 1,457 unresolved flags until supported by crop-level visual evidence or human review.
2. Implement the Gemini verifier as an optional, consent-gated provider with strict JSON validation and safe retries.
3. Keep protected content—names, dates, numbers, units, English, equations, question numbers, answer choices, and scientific terminology—human-reviewable even when Gemini is confident.
4. Do not write Gemini suggestions directly into literal output.
5. Measure changes only against the private, fully human-approved 30-page benchmark.
6. Report provider-order conflicts and severe-divergence flags separately from confirmed omissions or hallucinations.

Until those steps and the human benchmark are complete, the correct accuracy status is `UNMEASURED_PENDING_HUMAN_GROUND_TRUTH`.
