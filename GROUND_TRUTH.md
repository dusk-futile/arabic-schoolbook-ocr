# Private ground-truth workflow

The supplied book is `EVALUATION_ONLY`; its pages and annotations are ignored by Git and never enter training or validation.

1. Finish the checkpointed full-book Local job. The current acceptance job completed 209/209 pages.
2. Create the locked, unreviewed 30-page draft. The current draft exists with zero human-approved pages:

   ```powershell
   python scripts/create_ground_truth_manifest.py jobs/<full-book-job>
   ```

3. Open the job in the Review screen. On each selected page, compare every block with the source; correct exact text, type, order, boxes/structure, paragraph/boundary groupings, mixed-script runs, and table cells. Saving even unchanged text records explicit visual review; machine consensus is not approval.
4. After every text/table block on a page has a human-approval record, approve that page:

   ```powershell
   python scripts/approve_ground_truth_page.py `
     data/ground_truth/<job>/ground_truth_manifest.json `
     jobs/<job> 4 --reviewer "Reviewer name"
   ```

5. Complete all 30 pages. `GroundTruthManifest.assert_ready_for_metrics()` refuses scoring while any page remains unreviewed.

6. Evaluate each provider job separately:

   ```powershell
   python scripts/evaluate_job.py `
     data/ground_truth/<job>/ground_truth_manifest.json jobs/<provider-job>
   ```

   This writes JSON and HTML with per-page and aggregate OCR/structure metrics, latency, API usage, and estimated cost. Cross-mode comparison should use the same locked manifest.

The category labels in the initial selection are provisional and must be visually confirmed. Draft OCR cannot be copied into reference truth without comparison. Accuracy reports must keep `UNMEASURED_PENDING_HUMAN_GROUND_TRUTH` until the manifest passes the readiness assertion.
