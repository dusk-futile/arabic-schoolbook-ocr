# Demo data

Small, project-generated Arabic pages with **exact ground truth**, so anyone can
reproduce the accuracy numbers without a private book.

```
pages/indent_tight.pdf   3 pages, justified with a first-line indent and no
                         paragraph spacing - the hardest and most common
                         Arabic book layout
pages/two_col.pdf        2 pages, two columns, right-to-left reading order
pages/*.gold.json        the exact rectangle and text of every paragraph
```

`*.gold.json` records where each paragraph physically sits on the page, which
is what makes paragraph-boundary accuracy measurable rather than eyeballed.

## Try it

```bash
python demo/run_demo.py
```

That runs both paths and prints CER, WER, paragraph F1 and reading order
against the ground truth above.

## Provenance and licence

The page text is drawn from Arabic Wikipedia articles on psychology and
education, used under **CC BY-SA 4.0**. Source articles are listed in
`corpus/SOURCES.txt`. The page layouts, the generator and the ground-truth
annotations are project-authored and released under the repository licence.

No page here comes from any private or copyrighted book.
