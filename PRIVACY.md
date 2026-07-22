# Privacy policy and data flow

## Default behavior

Local mode processes PDF pages, model inference, reports, and DOCX files on the host. It requires no credential. Jobs and private ground truth are written under ignored local directories and are never intended for repository publication.

## Cloud consent

Azure Document Intelligence and Hybrid Verified modes fail closed unless the user supplies credentials and explicitly enables `cloud_opt_in` for that job. Consent records name the allowed providers and pages. Disabling consent prevents page bytes from being submitted.

Hybrid mode may send only selected low-confidence/disputed crops to Gemini. Formatting analysis and rendered-Word visual QA can send selected full pages only when their capability is enabled **and** the job records a separate full-page consent. All Gemini capabilities are off by default and were off in the acceptance run. Gemini is not used to summarize documents, and the formatting/QA roles cannot modify verified text or DOCX content.

Keys entered through Settings are held only in the running server process, are never returned by the API, and disappear when that process exits. A local `.env` is the explicit restart-persistent option and is ignored by version control.

Cloud providers may retain or log data according to the user's service configuration and contract. Before opt-in, review region, retention, abuse-monitoring, logging, and data-processing terms for the specific account. This project does not assert a universal provider-retention policy.

## Stored data

Each private job may contain the uploaded PDF, rendered pages, preprocessed images, overlays, provider JSON, crops, canonical text, annotations, reports, and exports. Delete the job directory according to your retention policy after delivery. Do not commit `jobs/`, `data/ground_truth/`, `.env`, or screenshots of private pages.

## Ground truth and training

The supplied acceptance book and its annotations are `EVALUATION_ONLY`, with `training_allowed=false`. They may be used for private measurement after human review, but not for training, validation, public samples, or redistribution. `TRAINING_APPROVED=false` is enforced by application settings.
