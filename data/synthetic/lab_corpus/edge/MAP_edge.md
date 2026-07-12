# Фаза 3 — edge-фикстуры для фуззинга парсера

Всего 23 файлов: CSV/TSV/PSV с разными разделителями и кодировками, бинарный .xls, xlsx-edge и вырожденные.

| Файл | Вендор | Формат | Quirks |
|---|---|---|---|
| `thornfield_cbc.csv` | Thornfield Labs | CSV (utf-8, comma) | clean-ish, operator_vals |
| `bluecrest_cmp.csv` | Bluecrest Diagnostics | CSV (cp1251, semicolon) | comma_decimal, cyrillic_encoding, comment_preamble, endash_in_range |
| `vantage_lipid.tsv` | Vantage Clinical | TSV (utf-8 BOM, tab) | bom, split_ref_cols, arrow_flags |
| `meadowlark_thyroid.txt` | Meadowlark Reference | Pipe-delimited (.txt) | pipe_delimiter, operator_vals |
| `silvarea_immuno.csv` | Silvarea BioLabs | CSV (latin-1, comma) | latin1_accents, comma_decimal_with_comma_delim, unquoted_comma_in_value, ragged_meta_row |
| `redwood_coag.csv` | Redwood Path | CSV (ragged) | ragged_rows, missing_fields, extra_fields, empty_result |
| `northwind_urine.csv` | Northwind Diagnostics | CSV (quoted) | embedded_newlines, embedded_commas, embedded_quotes |
| `cinder_tumor.csv` | Cinder Medical | CSV (preamble+footer) | preamble_junk, footer_lines, header_not_row1, blank_separator_lines |
| `pallas_allergy.csv` | Pallas Labs | CSV (two tables) | two_tables_one_file, different_schemas, blank_line_separator |
| `driftwood_pcr.csv` | Driftwood Clinical | CSV (mixed EOL) | mixed_line_endings, crlf_lf_cr, detected_notdetected |
| `umbra_cbc.xls` | Umbra Diagnostics | XLS (legacy binary) | ole2_biff, single_sheet |
| `foxglove_cmp.xls` | Foxglove Labs | XLS (legacy, multi-sheet) | ole2_biff, data_split_across_sheets |
| `quartz_cmp.xlsx` | Quartz Reference Lab | XLSX (merged cells in data) | vertical_merge_in_body, group_label_only_on_anchor_row |
| `beacon_lipid.xlsx` | Beacon BioMedical | XLSX (duplicate rows) | duplicate_analytes, corrected_vs_final, conflicting_values, exact_duplicate_row |
| `hollowoak_thyroid.xlsx` | Hollow Oak Labs | XLSX (numbers as text) | numbers_stored_as_text, mixed_number_types, leading_zeros, padded_text |
| `sundial_urine.xlsx` | Sundial Diagnostics | XLSX (multi-sheet data) | data_split_across_sheets, paged_sheets, trailing_sheet_different_schema |
| `willowmere_cbc.xlsx` | Willowmere Labs | XLSX (offset data) | leading_blank_rows_cols, data_starts_at_D3, merged_title |
| `cobblestone_coag.xlsx` | Cobblestone Clinical | XLSX (section rows) | merged_section_headers_in_body, subtotal_rows, non_data_rows_interspersed |
| `ashgrove_immuno.xlsx` | Ashgrove Diagnostics | XLSX (blank spacer cols) | blank_spacer_columns, floating_note_cell, non_contiguous_columns |
| `tidewater_empty.csv` | Tidewater Labs | CSV (empty) | zero_bytes |
| `emberline_headeronly.csv` | Emberline Path | CSV (header only) | header_only, no_data_rows |
| `glasswing_empty.xlsx` | Glasswing Diagnostics | XLSX (empty sheet) | empty_sheet, no_cells |
| `glasswing_headeronly.xlsx` | Glasswing Diagnostics | XLSX (header only) | header_only, no_data_rows |

## На что тестировать

- **Определение кодировки**: utf-8, utf-8+BOM, cp1251 (кириллица), latin-1 (акценты).
- **Определение разделителя**: `,` `;` `\t` `|`; неоднозначность запятая-десятичный + запятая-разделитель (silvarea).
- **Line endings**: CRLF/LF/одиночный CR в одном файле (driftwood).
- **Границы таблицы**: преамбула/футер (cinder), две таблицы в одном файле (pallas), рваные строки (redwood).
- **Кавычки**: запятые, переносы строк и кавычки внутри полей (northwind).
- **Бинарный .xls (OLE2/BIFF)**: одно- и многолистовые (umbra, foxglove).
- **xlsx-структура**: merge в теле данных (quartz), секции/подытоги (cobblestone), смещение данных на D3 (willowmere), пустые колонки-разделители (ashgrove), данные по нескольким листам (sundial), дубли/corrected (beacon), числа-как-текст (hollowoak).
- **Вырожденные**: 0 байт, только шапка, пустой лист (tidewater, emberline, glasswing).
