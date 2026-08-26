# Arabic lexicon

`ar_words.txt.gz` holds 294,137 Arabic stems derived from the LibreOffice
Arabic hunspell dictionary (`dictionaries/ar/ar.dic`), stripped of affix flags
and diacritics.

Upstream licence: GPL / LGPL / MPL tri-licence, as stated by the LibreOffice
dictionaries project. It is used here only as a wordlist for a spell-check
style membership test.

Rebuild with `python eval/build_lexicon.py`. The lexicon is optional: without
it the pipeline runs unchanged, minus the doubled-letter corrector.

## English wordlist

`en_words.txt.gz` holds 234,282 lowercase English words derived from the
`web2` wordlist (Webster's Second International Dictionary, 1934), which is in
the public domain and ships as `/usr/share/dict/words` on macOS and most BSD
systems.

It is used only to resolve damaged Latin glyphs in otherwise-Arabic documents —
academic citations and technical terms — by the same substitution test used for
Arabic. Without it, Latin runs keep whatever the PDF's own character map says.
