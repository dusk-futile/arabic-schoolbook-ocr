# License compatibility report

Audit date: 2026-07-22. Public availability is not treated as training permission.

## Release scenarios

| Source | Private non-commercial experiment | Public non-commercial weights | Public commercial weights | May redistribute source subset | Current decision |
|---|---:|---:|---:|---:|---|
| Arabic E-Book Corpus, CC BY 4.0 | Yes | Yes, with attribution | Yes, with attribution | Yes, with attribution | Green |
| Arabic-Img2MD, GPL-3.0 card plus undocumented Hindawi work selection | Review required | No | No | No | Hold |
| Arabic-Nougat weights, GPL-3.0 | Evaluation only | Review required | Review required | Weights only under GPL conditions | Hold for derivative release |
| SARD, CC BY-NC-ND plus Alukah restrictions | No until written permission/legal review | No | No | No | Blocked |
| OpenITI Arabic Print Data, exact repo unlicensed | No | No | No | No | Blocked |
| Supplied private book, `EVALUATION_ONLY` | Evaluation only | No | No | No | Acceptance only |

## Compatibility conclusions

1. **Only the Arabic E-Book Corpus is currently eligible for training-related work.** It may feed tokenizer analysis and locally generated synthetic pages, provided attribution and per-book provenance survive every transformation.
2. **SARD cannot be mixed into a commercial or publicly redistributed model under the audited terms.** Its non-commercial/no-derivatives label and explicit Alukah source restrictions are incompatible with the intended flexible release.
3. **Arabic-Img2MD is not cleared merely because its card says GPL-3.0.** The paper documents scraping Hindawi HTML but does not prove that each work allowed that use or redistribution. A public model trained on it needs source-rights confirmation and a decision on how GPL obligations apply to weights.
4. **OpenITI is a no-license stop.** General project statements cannot substitute for the exact repository and per-image rights the user required.
5. **The private acceptance book is not a license pool.** It may measure quality but cannot contribute gradients, prompts saved as training examples, validation tuning, hard-example mining, or correction training.

## Combination matrix

| Combination | Internal experiment | Public non-commercial release | Public commercial release | Decision |
|---|---:|---:|---:|---|
| CC BY 4.0 Arabic E-Book synthetic pages only | Yes | Yes | Yes | Allowed after attribution/font audit |
| Arabic E-Book + Arabic-Img2MD | Review | No | No | Keep separate until provenance/GPL review |
| Any source + SARD | No | No | No | Incompatible under current terms |
| Any source + OpenITI exact repo | No | No | No | Unlicensed input |
| Any training source + private acceptance book | No | No | No | Leakage and permission violation |

## Isolation rule

If a held resource is later approved, it receives a source-specific dataset version and a source-specific adapter/experiment. No public merged checkpoint is produced until a written compatibility review explicitly lists every included dataset revision.

## Approval gate

`TRAINING_APPROVED = false`

Approval of this report would authorize only the green Arabic E-Book workflow described in the subset proposal. It would not authorize SARD, Arabic-Img2MD, OpenITI, the private book, model-weight downloads, cloud processing, or a full training run.
