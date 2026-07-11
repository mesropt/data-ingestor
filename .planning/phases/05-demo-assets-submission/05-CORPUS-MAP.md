# Phase 5 Corpus Map — DEMO-01 / DEMO-02 evidence

Verified by reading the actual files (pandas/openpyxl) on 2026-07-11, not by
trusting the existing manifests alone. Existing manifests were read and cited
as ground-truth *claims*; every claim in this doc was cross-checked against
real bytes read from the file. Script used:
`/tmp/claude-1000/.../scratchpad/dump_corpus.py` (headers/sheets/first rows via
openpyxl `iter_rows` and raw-line reads for CSV/TSV/TXT). All commands run
read-only — no data file was modified.

Corpus inventory actually on disk:

| Location | File count | Purpose |
|---|---|---|
| `data/synthetic/` (top level) | 20 files (16 `.xlsx`, 4 `.csv`) | Assay/potency-style vendor fixtures + 1 non-assay domain proof |
| `data/synthetic/lab_corpus/` | 30 `.xlsx` + `MAP.md` + `README.md` + `manifest.json` | Clinical-lab-report corpus, second domain |
| `data/synthetic/lab_corpus/edge/` | 23 files (2 `.xls`, mixed CSV/TSV/TXT/XLSX) + `MAP_edge.md` + `manifest_edge.json` | Parser-killer edge cases |
| `data/synthetic/lab_corpus/wild/` | 20 files (HL7/ASTM/FHIR/CDA/HTML/PDF/fixed-width/ZIP + some `.xlsx`/`.csv`) + `MAP_wild.md` + `README.md` + `manifest_wild.json` | Out-of-scope format negative cases + a few unhardened `.xlsx`/`.csv` gaps |

Existing manifests (`data/synthetic/README.md`, `lab_corpus/MAP.md` +
`manifest.json`, `edge/MAP_edge.md` + `manifest_edge.json`, `wild/MAP_wild.md`
+ `manifest_wild.json`) already document per-file intent in detail (the
`lab_corpus`/`edge`/`wild` maps are written in Russian). They were read in
full and used as a index, but every claim below reflects what the actual
bytes show, verified independently.

---

## DEMO-01 — domain coverage (at least 3 distinct domains, not 2)

| Domain | Field vocabulary | Files (location) |
|---|---|---|
| **Assay / potency** | `compound_id`, `assay_type` (IC50/EC50/Ki/Kd/%inhibition), `value`, `unit` (nM/µM/%), `target` (EGFR/JAK2/BRAF/…), `n_replicates`, `assay_date` | All 20 top-level `data/synthetic/*.{xlsx,csv}` **except** `verity_reagents_stock.xlsx`: `apex_labs_wide_matrix.xlsx`, `bionexus_transposed.xlsx`, `cascade_assays_nounit.xlsx`, `castlebio_native_dates.xlsx`, `crestchem_results.csv`, `delta_screening_per_target.xlsx`, `helix_genomics_DE.xlsx`, `helixbio_export.csv`, `meridian_cro_codes.xlsx`, `nimbus_labs_chartsheet.xlsx`, `novascreen_batch01/02.csv`, `orion_pk_report.xlsx`, `pinnacle_labs_export.csv`, `quantex_scanned_report.xlsx`, `summit_discovery_mixed.xlsx`, `triton_screening_two_tables.xlsx`, `vantage_pk_with_chart.xlsx`, `vertex_pk_eu_format.xlsx`, `zephyr_bio_ZB-2025.xlsx` |
| **Clinical lab report** | `Analyte`/`Test`, `Result`, `Units`, `Reference Interval`/`Range`, `Flag`, `LOINC`, patient demographics (MRN, DOB, Accession) — a completely different field set (no `compound_id`, no `assay_type`, no `target`) | All 30 files in `data/synthetic/lab_corpus/*.xlsx` — panels: CBC, CMP, lipid, thyroid, coag, PCR, immuno, tumor, allergy, urine (verified: `cobalt_cbc_*`, `sequoia_cmp_*`, `halcyon_lipid_*`, `ironwood_thyroid_*`, `nimbus_urine_*`, `quill_coag_*`, `tessera_pcr_*`, `larkspur_immuno_*`, `osprey_tumor_*`, `verdant_allergy_*`, and 20 more — headers read directly, e.g. `wuxi_cbc_WX-2026-142700.xlsx::CBC Results` row3 = `('Test / Analyte', 'Result', 'Flag', 'Units', 'Reference Interval', 'LOINC')`) |
| **Reagent inventory** (domain-independence proof, zero shared vocabulary) | `SKU`, `Item`, `On hand`, `Units`, `Use By`, `Location`, `Reordered?` — no assay/lab-result word appears anywhere | `verity_reagents_stock.xlsx` — verified sheet `Stock on hand`, header row 3: `('SKU', 'Item', 'On hand', 'Units', 'Use By', 'Location', 'Reordered?')`, e.g. row `('AB-11023', 'Anti-FLAG M2 antibody', 2.5, 'mL', '2026-03-01', 'Freezer B / rack 4', 'no')` |

**Conclusion: DEMO-01 is satisfied with margin** — 3 domains, not the minimum
2, spanning 51 real files (20 top-level + 30 lab_corpus + 1 reagent file
already counted in top-level). `verity_reagents_stock.xlsx` is the strongest
single artifact: it is explicitly built (per its own README section, cited
and verified below) to prove the tool carries zero hardcoded assay
vocabulary — it maps against `presets/reagent-inventory.yaml`, a field set
that shares no words with the assay field set.

---

## Same-signature pair (learning-loop money shot)

Verified programmatically using the project's own
`src/assayingest/learning/signature.py::column_signature()` (order-independent,
duplicate-preserving, case/whitespace-tolerant hash) against the real CSV
headers:

```
novascreen_batch01.csv headers: ['cmpd', 'assay', 'potency', '', 'target_gene', 'replicates', 'date']
novascreen_batch02.csv headers: ['cmpd', 'assay', 'potency', '', 'target_gene', 'replicates', 'date']
sig1 == sig2 → True  (both hash to 6a7a8e3d1c34...)
```

Both files carry the same blank 4th header (the unit column is genuinely
absent, not just unlabeled) and the same 7-column shape. Potency value
ranges differ but both sit inside the nM band the mapper infers from:
`batch01` 0.8–880, `batch02` 0.7–930 — consistent with the README's
"infer nM from range" claim.

**This is the confirmed learning-loop pair**, exactly as documented in
`data/synthetic/README.md`'s "Demo narrative" section.

### Other same-signature groups found (side note, not the primary pair)

Running the same signature function's first-row headers across every
top-level and `lab_corpus`/`edge` file surfaced two more incidental (not
purpose-built) matches, useful as backup material if needed:

- `nimbus_labs_chartsheet.xlsx` (sheet `Data`), `triton_screening_two_tables.xlsx` (sheet `Combined`), and `vantage_pk_with_chart.xlsx` (sheet `Results`) all share the exact header row `('Compound', 'Assay', 'Result', 'Unit', 'Target', 'Replicates', 'Date')` — three different "vendors" that happen to use the clean canonical layout (each exists for a different D-16/D-17/D-10 structural reason, not as a learning-loop pair).
- `lab_corpus/edge/cobblestone_coag.xlsx`, `emberline_headeronly.csv`, `glasswing_headeronly.xlsx`, `hollowoak_thyroid.xlsx`, `sundial_urine.xlsx` (first sheet) all share `('Analyte', 'Result', 'Units', 'Reference', 'Flag')` — again incidental, these are independent edge fixtures for unrelated hazards (numbers-as-text, header-only, multi-sheet, etc.), not a designed lab-repeat pair.

Several `lab_corpus` "row 1" matches (`aldercreek_tumor` vs `larkspur_immuno`;
the 9-file `'LABORATORY REPORT'` group) are **not** real signature matches in
the sense that matters — row 1 in those files is a title/preamble row, not
the real header (the real header sits several rows down, per-file), so the
parser's actual header-detection would not treat these as the same column
signature. Excluded from the claim above.

---

## DEMO-02 — hazard coverage (7 requested hazards)

| # | Hazard | Status | Covering file(s) — verified detail |
|---|---|---|---|
| 1 | Unit ambiguity / missing unit | **Covered** | `novascreen_batch01/02.csv` — blank 4th header, unit inferred from value range (0.7–930 → nM). `cascade_assays_nounit.xlsx` — header row `('cmpd', 'potency', None, 'target_gene', '#', 'run')`, no unit column at all, plus a `None`-named QC-flag junk column. `crestchem_results.csv` — mixes `Inhibition %` (unit `%`) and `IC50`/`Kd` (unit `nM`) in one file. `apex_labs_wide_matrix.xlsx` — unit lives only in the sheet name `'IC50 matrix (nM)'`, never a column. |
| 2 | Ambiguous / serial (Excel-serial / locale) dates | **Covered** | Locale variety verified across files: `helixbio_export.csv` (`DD/MM/YYYY`, ambiguous vs `MM/DD`), `meridian_cro_codes.xlsx` (`DD-MM-YYYY`), `helix_genomics_DE.xlsx` / `vertex_pk_eu_format.xlsx` (`DD.MM.YYYY`), `orion_pk_report.xlsx` (`YYYY/MM/DD`), `apex_labs_wide_matrix.xlsx` (`MM/DD/YYYY`), `summit_discovery_mixed.xlsx` (unpadded `M/D/YYYY`), `cascade_assays_nounit.xlsx` (compact `YYYYMMDD`, e.g. `'20250101'`). Native-typed cell: `castlebio_native_dates.xlsx` — cell value is a real `datetime.datetime(2025, 1, 1, 0, 0)` object, not text. Mixed-format-in-one-file: `lab_corpus/quill_coag_QF2630229.xlsx` row4 has `Received='13/07/2026'` next to `Reported='07/14/26 13:44'` in the same sheet; `lab_corpus/marlowe_cmp_MD2663923.xlsx`/`sequoia_cmp_SB2668369.xlsx` show the same `Colected`/`Recieved` dual-date pattern. Serial-date corruption (unhardened, tracked): `lab_corpus/wild/10_genelab_date_disaster.xlsx` — gene names and titers silently auto-converted by Excel into `datetime` objects (e.g. `'SEPT9 methylation'` result cell reads as `datetime.datetime(2026, 9, 1, 0, 0)`), documented in `wild/README.md` as a known gap for the parser-hardening phase, not yet solved — still a real covering file. |
| 3 | Blank headers **and** duplicate headers | **Partially covered — GAP on duplicate headers** | Blank headers: `cascade_assays_nounit.xlsx` (3rd header is `None`), `novascreen_batch01/02.csv` (4th header is `''`), `lab_corpus/edge/glasswing_headeronly.xlsx` / `emberline_headeronly.csv` (header row present, zero data rows), `lab_corpus/willowmere_cbc.xlsx` (leading blank columns A–C before the real header at D3). **Duplicate column headers were checked exhaustively (every `.xlsx`/`.csv`/`.tsv`/`.txt` header-like row, first ~15 rows per sheet, both column-position and CSV-line splits on `,`/`;`/tab/`\|`) and NONE was found** — every apparent "duplicate" hit was a data row in a transposed/matrix layout (e.g. `bionexus_transposed.xlsx` row2 repeating `Ki`/`IC50` are *values*, not header names) or a coincidental repeated date/number in a demographics row, never two columns of a real header row sharing one name. **GAP: no file in the corpus has a genuine duplicate-named header column** (e.g. two columns both literally titled `Result`). Recommend generating one if this specific sub-hazard needs to be demoed or tested. |
| 4 | Preamble / junk rows above the real header | **Covered** | `zephyr_bio_ZB-2025.xlsx` — 4 metadata/title rows above the header on every one of its 3 sheets (`'ZEPHYR BIOSCIENCES — Kinase Panel...'`, study director, report-generated line, blank row, then the real header on row 5). `pinnacle_labs_export.csv` — 2 `#`-prefixed comment lines before the header. `lab_corpus/edge/cinder_tumor.csv` — lab letterhead + accession + blank lines + patient line before data (also ragged rows, breaks `pd.read_csv` with "Expected 8 fields... saw 10"). `verity_reagents_stock.xlsx` — title row + blank row before header on row 3. `lab_corpus/willowmere_cbc.xlsx` — merged title + blank row + real header at `D3` (data starts even further right, at column D). `lab_corpus/tessera_pcr_TM2641797.xlsx` / `zenith_pcr_ZB2624633.xlsx` — leading `Notice`/`Index`/`READ ME` junk sheets ahead of the real `Report` sheet. |
| 5 | Delimiter variance (semicolon/tab/comma; decimal-comma locale) | **Covered** | `pinnacle_labs_export.csv` — semicolon-delimited, comma-decimal values (`'11,076'`), explicit self-declared header comment `delimiter=';'; decimal=','`. `data/synthetic/lab_corpus/edge/vantage_lipid.tsv` — tab-delimited with a UTF-8 BOM (`'﻿Test\tValue\tUnit...'`). `lab_corpus/edge/meadowlark_thyroid.txt` — pipe-delimited (`Analyte\|Result\|Units\|...`). `lab_corpus/edge/bluecrest_cmp.csv` — semicolon-delimited, `cp1251` (Cyrillic) encoded, comma-decimal (`'0,80'`). `lab_corpus/wild/16_alpenlab_nbsp.csv` — semicolon-delimited, comma-decimal, values glued to NBSP-separated units (`'5,0\xa0%'`). `lab_corpus/wild/18_orchid_sep_hint.csv` — semicolon-delimited with an Excel `sep=;` hint line and BOM. `helix_genomics_DE.xlsx`/`vertex_pk_eu_format.xlsx` — comma-decimal inside `.xlsx` text cells (`'14,771'`, `'3.698,10'` — the latter is true EU thousands-`.`+decimal-`,` format, distinct from bare comma-decimal). |
| 6 | Multi-sheet workbook needing sheet selection | **Covered** | `orion_pk_report.xlsx` — 3 sheets (`Summary` = real data, `Raw timepoints` = alt granularity, `Notes` = single free-text cell); README states the tool "must pick the right sheet." `meridian_cro_codes.xlsx` — `DATA` (real) + `LEGEND` (code glossary, not data). `delta_screening_per_target.xlsx` — 3 sheets (`EGFR panel`/`JAK2 panel`/`BRAF panel`), each real data but with a differently-spelled header per sheet. `nimbus_labs_chartsheet.xlsx` — a real `Data` sheet plus a `Chart Overview` **chartsheet** (not a regular `Worksheet`; `openpyxl` raises `'Chartsheet' object has no attribute 'dimensions'` when treated as one, confirming it must be excluded from sheet ranking, not crash the reader). `lab_corpus/aurora_pcr_AU-2026-870185.xlsx` and most `lab_corpus` "full report" files ship 8–9 sheets (`Report Summary`, `Patient & Specimen`, real results sheet, `Reference Ranges`, `Historical Trend`, `Result Visualization` (chart-only, structurally empty), `Quality Control`, `Methodology & Notes`) — real multi-sheet selection pressure at scale. |
| 7 | Unfamiliar structure needing a human hint (PARSE-06) | **Covered — strongest example is documented and pinned by a test** | `verity_reagents_stock.xlsx` — header sits on row 3 under a merged title row and a blank row; `data/synthetic/README.md` states explicitly: "the parser stops and asks rather than guessing (`--hint header-row=2`)... Live result: all six fields map at confidence 1.00... Export unblocks (exit code 0)... Pinned by `tests/test_cross_domain.py`." Also genuinely unfamiliar shapes present: `bionexus_transposed.xlsx` (fields as rows, compounds as columns — transposed/matrix), `apex_labs_wide_matrix.xlsx` (wide: one IC50 column per target), `triton_screening_two_tables.xlsx` (two independent tables on one sheet, separated by 2 blank rows), `quantex_scanned_report.xlsx` (image-only sheet, `A1:A1` empty dims, no cells at all — must surface a structural question, not a silent "no data rows" skip). `lab_corpus/ironwood_thyroid_IP2619115.xlsx` (matrix layout), `lab_corpus/verdant_allergy_VB2691001.xlsx`/`kestrel_cbc_KC2627955.xlsx` (wide format), `lab_corpus/sequoia_cmp_SB2668369.xlsx`/`sablefish_lipid_SL2671274.xlsx` (multi-table-per-sheet). |

**Hazard coverage: 6.5 / 7.** Six of seven hazards have solid, multi-file
coverage; the seventh ("blank headers and duplicate headers") is covered on
the blank-header half only — **no file in the entire corpus contains a
genuine duplicate column-name header row**, confirmed by an exhaustive
programmatic scan (header-like rows, first ~15 rows of every sheet, split on
every plausible delimiter). This is a real, generatable gap if the demo or
test suite specifically needs "two columns both named `Result`."

---

## Demo-ready shortlist (3 files for the ≤3-min video)

| Slot | File | Hazard shown | What the reviewer sees |
|---|---|---|---|
| (a) Messy-file money shot | `data/synthetic/crestchem_results.csv` | Mixed assay types in one file (`Inhibition %` rows next to `IC50`/`Kd` rows), mixed units (`%` vs `nM`) that must be read per-row not per-column, and a leading space in the ` ID` header that must be stripped/normalized. | Small CSV (5 rows, fast to render), upload → structured draft in ~5s, with the assay-type/unit columns showing Claude's per-row disambiguation and the stripped header — a single file that visibly demonstrates 3 hazards resolving into a clean table, ideal for the opening "define → upload → clean output" beat. |
| (b) Learning-loop shot | `novascreen_batch01.csv` → `novascreen_batch02.csv` | Missing unit column (blank 4th header) inferred from value range on the first upload (yellow, needs confirmation); identical column signature (verified via `column_signature()`, confirmed hash match) on the second upload from "the same lab." | First upload: several fields, at least `unit`, land yellow with Claude's stated reasoning ("no unit column; inferred nM from value range 0.8–880"). Curator confirms once, mapping saves as a lab profile keyed by the signature above. Second upload (batch02): **zero yellow fields**, everything auto-maps at confidence 1.0 with no Claude call — the differentiator, visibly proven on screen. |
| (c) Human-structural-hint shot | `verity_reagents_stock.xlsx` | PARSE-06: header on row 3 under a merged title + blank row, and a totally different domain (reagent inventory: `SKU`/`Item`/`On hand`/`Use By`/`Location`) with zero shared vocabulary with the assay field set. | Upload triggers a structural question instead of a silent guess or a crash; curator answers "header is row 3" inline; re-parse succeeds and all 6 fields map at confidence 1.00 against the `reagent-inventory` preset — doubles as the domain-independence proof (a completely different field set with no assay/lab-result words maps cleanly) and the "asks instead of guessing" proof in the same clip. |

This 3-file set (4 physical files counting the novascreen pair) covers:
domain independence (crestchem = assay domain, verity = reagent domain),
the learning loop (novascreen pair), and the human-structural-hint fallback
(verity) — the three headline claims the video needs to prove, each backed
by a file actually read and verified above.
