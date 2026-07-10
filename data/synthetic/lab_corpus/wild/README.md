# Wild formats — real lab-interchange, mostly out of scope

The formats a lab actually emits: HL7 v2 (`.hl7`), ASTM/LIS2-A2 and fixed-width
(`.txt`), FHIR R4 (`.json`), CDA R2 (`.xml`), an HTML report, a PDF, a ZIP
batch — plus genuinely messy `.xlsx`/`.csv`. Ground truth in `manifest_wild.json`
and `MAP_wild.md`. All synthetic.

## Scope decision this corpus pins

AssayIngest ingests **spreadsheets only** (`.xlsx`, `.csv`) — a data curator
reformats the Excel/CSV a CRO hands them, not machine-to-machine interchange.
`tests/test_wild_formats.py` holds both halves:

- Every unsupported format (HL7/FHIR/CDA/HTML/PDF/fixed-width/ZIP) is **refused
  with a named error** that says what the tool accepts — never parsed on a guess.
- Every supported spreadsheet, however messy, resolves to a table, a structural
  question, or a named error — never a raw traceback.

The 1.1 MB `08_scanned_fax.pdf` from the source set is intentionally **not**
vendored: a second `.pdf` adds nothing to an extension-refusal test.

## Applicable files with known silent-handling gaps

These `.xlsx`/`.csv` parse without crashing but are not yet handled *well*
(sep=/BOM hints, ragged rows, homoglyph headers, NBSP-glued units, Excel error
strings, date auto-corruption, multi-row headers, hidden cells, references in
comments). Tracked in `.planning/todos/pending/` for the parser-hardening phase,
not fixed here.
