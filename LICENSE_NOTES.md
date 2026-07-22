# License notes

## Separation of concerns

- **Application code license** does not license datasets or model weights.
- **Model-weight license** does not cure restrictions in training sources.
- **Dataset license** does not automatically license third-party text, fonts, images, or templates embedded in it.
- **Evaluation permission** is not training permission.

## Current code and model foundation

- Unlimited-OCR code revision `1ab6b46...` and weight revision `2a06ebf...` declare MIT. Preserve notices if vendored or redistributed.
- Arabic-Nougat repository revision `9c0b9a6...` has no standalone license file; its README says CC BY-SA 4.0. Do not vendor it until clarified.
- Arabic-Nougat weights separately declare GPL-3.0. Treat them independently from repository code.

## Release rule

Every release candidate needs a generated bill of materials listing:

```text
application source and commit
base-model weights and revision
adapter weights and experiment
training dataset versions
font/template/image assets
inference and training frameworks
required copyright notices
attribution text
share-alike/copyleft obligations
commercial-use decision
redistribution decision
```

No public checkpoint is approved by the current audit.
