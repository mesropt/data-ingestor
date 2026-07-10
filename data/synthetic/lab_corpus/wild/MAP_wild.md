# Фаза 4 — «дикие» реальные форматы лабораторного обмена

20 файлов. Форматы из настоящей практики LIS/EHR/приборов и стандартов обмена.

| Файл | Формат | «Вендор» | Что ломает парсер |
|---|---|---|---|
| `01_wuxi_ORU_R01.hl7` | HL7 v2.5 ORU^R01 | WuXi | hl7v2, pipe_caret_delimiters, CR_segment_sep, OBX_segments, Z_segment, NTE_notes |
| `02_sysmex_LIS2A2.txt` | ASTM E1394 / LIS2-A2 | Sysmex | astm, H_P_O_R_L_records, frame_numbers, caret_subfields, crlf |
| `03_labcorp_FHIR_R4.json` | FHIR R4 Bundle (JSON) | LabCorp | fhir_r4, nested_resources, reference_by_id, valueQuantity, referenceRange_objects, interpretation_codes |
| `04_acme_vendor.json` | Vendor JSON (ugly) | Acme LIS | inconsistent_keys, value_str_vs_num, unit_vs_units, ref_string_vs_object_vs_array, null_vs_empty, object_instead_of_array, value_with_glued_unit |
| `05_quest_CDA.xml` | HL7 CDA R2 (XML) | Quest | cda_xml, namespaces, xsi_types, nested_referenceRange, oid_codesystems |
| `06_meditech_report.html` | HTML LIS report | MEDITECH | nested_tables, colspan_rowspan_header, data_in_attributes, flag_by_color_only, two_row_thead |
| `07_bioreference_report.pdf` | PDF (text layer, table) | BioReference | pdf_table, extractable_text, flag_by_color, reportlab |
| `08_scanned_fax.pdf` | PDF (image-only / scanned) | Quantum | no_text_layer, requires_ocr, scan_noise, slight_skew, monospace_fax |
| `09_hologic_fixedwidth.txt` | Fixed-width text + OCR | Hologic | fixed_width_columns, no_delimiter, ocr_char_substitution, space_padded_alignment |
| `10_genelab_date_disaster.xlsx` | XLSX (Excel auto-conversion) | GeneLab | gene_names_as_dates, titer_as_time, ratio_as_date, sample_id_as_scientific, raw_serial_date, silent_data_corruption |
| `11_horizon_error_values.xlsx` | XLSX (error values) | Horizon | excel_error_strings, REF_DIV0_NA_VALUE, live_error_formulas, values_paste_artifacts |
| `12_kaiser_crosstab.xlsx` | XLSX (cross-tab / pivot) | Kaiser | pivoted_dates_as_columns, longitudinal, merged_super_header, two_row_header |
| `13_sonora_multiheader.xlsx` | XLSX (multi-level header) | Sonora Quest | two_row_header, merged_group_headers, header_needs_concatenation |
| `14_carbon_hidden.xlsx` | XLSX (hidden rows/cols) | Carbon Health | hidden_rows_superseded, hidden_column_true_value, autofilter, visible_vs_hidden_mismatch |
| `15_probe_ref_in_comments.xlsx` | XLSX (reference in cell comments) | Probe Dx | reference_only_in_comments, no_reference_column, method_loinc_in_notes |
| `16_alpenlab_nbsp.csv` | CSV (NBSP / glued units) | AlpenLab | nbsp_u00a0, thousands_space_sep, comma_decimal, unit_glued_to_value, semicolon_delim |
| `17_medlab_homoglyphs.csv` | CSV (homoglyph headers) | MedLab RU | cyrillic_latin_homoglyphs, mixed_script_headers, cyrillic_units, utf8_confusables |
| `18_orchid_sep_hint.csv` | CSV (sep= hint + BOM) | Orchid | excel_sep_hint_line, bom, delimiter_inside_quotes, semicolon_in_ref_range |
| `19_apex_mixed_types.csv` | CSV (mixed types in column) | Apex Molecular | scientific_notation, operator_values, qualitative_mixed_with_quant, log_notation, comma_in_number, status_codes |
| `20_dailybatch.zip` | ZIP batch (mixed formats) | Daily Courier | zip_archive, nested_folders, mixed_formats_inside, csv_xlsx_hl7_together |

## Заметки по стандартам (официальная документация)

- **HL7 v2.x** (сегменты MSH/PID/OBR/OBX, разделители `|^~\&`, сегменты через CR `\r`) — спецификация HL7 International.
- **ASTM E1394 / CLSI LIS2-A2** — протокол вывода приборов, записи H/P/O/R/L, субполя через `^`.
- **HL7 FHIR R4** — ресурсы `DiagnosticReport` и `Observation` (`valueQuantity`, `referenceRange`, `interpretation`), ссылки по id.
- **HL7 CDA R2** — XML с namespace `urn:hl7-org:v3`, `xsi:type`, OID-системы кодирования.
- **Excel auto-conversion** — известная проблема: гены (SEPT9/MARCH1) и соотношения/титры превращаются в даты; ID → научная нотация. См. рекомендации HGNC по именам генов.
