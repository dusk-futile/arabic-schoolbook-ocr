# Synthetic public demo

This fixture exercises Arabic RTL text, an embedded English phrase, Western digits, Arabic punctuation, a question, a list, a figure/caption, a real table, and a page number.

Regenerate it with:

```powershell
python scripts/create_demo_fixture.py
```

All content is project-authored and released under [CC0](LICENSE.md). It is safe to publish and must not be replaced with a page from the private acceptance book.

Generated output includes literal/polished DOCX files, structural validation JSON, a locally converted PDF, and a rendered PDF page image. The validation checks logical text, RTL OOXML, real table structure, embedded figures, and package integrity.
