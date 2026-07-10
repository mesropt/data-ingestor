---
kind: enhancement
area: parsing
surfaced_by: data/synthetic/lab_corpus
created: 2026-07-10
---

# Detect non-UTF-8 CSV encodings instead of refusing them

`edge/bluecrest_cmp.csv` (Windows-1251, Cyrillic) and `edge/silvarea_immuno.csv`
(Latin-1, accented names) are currently refused with a named "not UTF-8" error.
A real curator's regional export should be read, not bounced.

Approach: sniff encoding (charset-normalizer / chardet, or a BOM + byte-heuristic
pass) before `pd.read_csv`, and thread the detected encoding through. Decide
whether to add a dependency or ship a small built-in heuristic. Belongs in the
parser-hardening phase, alongside the existing delimiter/locale detection.

silvarea also mixes a comma decimal separator with a comma field delimiter —
verify locale annotation still holds once the file is readable.

## Update (wild corpus, 2026-07-10)

- `wild/17_medlab_homoglyphs.csv` — headers mix Cyrillic look-alikes into Latin
  words (`AnalИte`, `Сholesterol`), and units are Cyrillic (`мg/dL`). Detect /
  normalise confusable homoglyphs so a column is not silently split into two
  distinct-looking names.
- `wild/16_alpenlab_nbsp.csv` — semicolon-delimited, comma decimals, and a
  non-breaking space (U+00A0) gluing the unit to the value (`5,0␠%`). The unit
  should separate from the number and the NBSP not corrupt the numeric parse.
