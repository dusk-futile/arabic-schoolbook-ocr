# Implementation plan

## Current gate

`TRAINING_APPROVED = false`

## Milestones

1. **Licensing and baseline audit - complete**
   - Record exact revisions and code/data/weight distinctions.
   - Inventory the private book and lock it to acceptance.
   - Run local native-extraction and independent Windows Arabic OCR baselines.
2. **Phase 2 product implementation - complete**
   - Provider architecture, canonical schema, checkpoints, privacy gates, review UI, and DOCX reconstruction.
   - Five-page Local smoke workflow, regression fixtures, container, and CI.
3. **Green dataset materialization - not started**
   - Download only Version 1 metadata and required texts.
   - Select 175 complete books deterministically.
   - Audit every font/template/visual asset.
   - Generate and validate a 5,000-page synthetic pilot.
4. **Human ground-truth baseline - draft workflow implemented, correction pending**
   - Correct and approve the locked 30 representative pages from the private acceptance book.
   - Report CER, WER, digits, English, reading order, and structure with confidence intervals.
   - Acquire a compatible local GPU before the official Unlimited-OCR run, or obtain explicit external-processing approval.
5. **One-step training proof - prohibited until new approval and data validation**
   - One sample, one optimizer step, save/reload adapter, local inference.
   - This is not a full run and still requires an approved dataset manifest.
6. **Full training - explicitly gated**
   - Requires a locked split, measured baseline, successful dry run, complete license matrix, cost/hardware plan, and user approval of the named experiment.

## Stop conditions

- Empty or ambiguous source identity.
- No license on exact data revision.
- Non-commercial/no-derivatives source in a planned commercial/public model.
- Any private acceptance family appears in train or validation manifests.
- Cross-split duplicate or edition-family leakage.
- Attempt to send a private page to an external API without explicit approval.
