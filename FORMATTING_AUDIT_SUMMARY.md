# Ten-page Word formatting audit summary

Run date: 2026-07-22
Automated visual comparison: `NEEDS_CORRECTION`
Human approval: `0/10 — PENDING`

The current 209-page Word output has the correct page count and preserves semantic headings, real tables, source figure crops, RTL/LTR runs, headers/footers, lists, and source page boundaries. A side-by-side contact sheet of pages 1, 2, 4, 36, 53, 88, 143, 184, 188, and 209 nevertheless shows a consistent visual defect: content is compressed toward the top of the Word page, while source-relative vertical spacing and the scale/position of tables and figures are not reproduced closely enough.

Representative findings:

- title and heading content loses source centering and vertical hierarchy;
- dense paragraphs reflow into a much smaller upper-page region, compounded by unresolved OCR omissions;
- questions and mixed Arabic/English lines need line-by-line order and wrapping review;
- tables remain editable but are underscaled or positioned too high;
- figures remain present but lose source-relative vertical placement and caption spacing.

The detailed private HTML/Markdown audit and its rendered/source images remain beside the ignored evaluation job. No fidelity percentage is calculated from these pages, and none is marked passed. Deterministic Word changes are structurally tested; source-faithful page composition remains an open release limitation.
