# Карта messy-файлов (ground truth для тестов парсера)

Всего 20 файлов. Ниже — какой вендор, панель, раскладка и какие quirks заложены.

| Файл | Вендор | Панель | Раскладка | Quirks |
|---|---|---|---|---|
| `cobalt_cbc_CC2696371.xlsx` | Cobalt Clinical Labs | CBC | long | blank_rows, flag_inline, header_offset, merged_headers, typos, unicode_units |
| `sequoia_cmp_SB2668369.xlsx` | Sequoia BioMedical | CMP | multitable | comma_decimal, junk_sheets, multi_table, scattered_meta, typos |
| `halcyon_lipid_HR2636444.xlsx` | Halcyon Reference Lab | LIPID | long | combined_ref, num_as_text, trailing_spaces, typos, unit_inline |
| `ironwood_thyroid_IP2619115.xlsx` | Ironwood Pathology | THYROID | matrix | matrix, operator_vals, typos, unicode_units |
| `nimbus_urine_ND2648277.xlsx` | Nimbus Diagnostics | URINE | long | blank_cols, color_only_flag, footnote_rows, pending_states, typos |
| `quill_coag_QF2630229.xlsx` | Quill & Fenwick Labs | COAG | long | merged_headers, mixed_dates, operator_vals, scattered_meta |
| `tessera_pcr_TM2641797.xlsx` | Tessera Molecular | PCR | long | junk_sheets, multiline_cells, pending_states, typos |
| `larkspur_immuno_LH2676500.xlsx` | Larkspur Health Labs | IMMUNO | two_patient | blank_rows, thousands_sep, two_patients, typos |
| `osprey_tumor_OA2673547.xlsx` | Osprey Analytical | TUMOR | long | combined_ref, num_as_text, operator_vals, typos |
| `verdant_allergy_VB2691001.xlsx` | Verdant BioSciences | ALLERGY | wide | typos, unicode_units, wide_format |
| `kestrel_cbc_KC2627955.xlsx` | Kestrel Clinical | CBC | wide | flag_inline, trailing_spaces, wide_format |
| `marlowe_cmp_MD2663923.xlsx` | Marlowe Diagnostics | CMP | long | comma_decimal, header_offset, multiline_cells, scattered_meta, typos |
| `sablefish_lipid_SL2671274.xlsx` | Sablefish Labs | LIPID | multitable | blank_rows, junk_sheets, multi_table, typos, unit_inline |
| `onyx_thyroid_OM2647632.xlsx` | Onyx Medical Labs | THYROID | long | merged_headers, operator_vals, pending_states, typos, unicode_units |
| `perch_urine_PD2686022.xlsx` | Perch Diagnostics | URINE | long | color_only_flag, footnote_rows, num_as_text, typos |
| `fjord_coag_FR2616564.xlsx` | Fjord Reference Labs | COAG | matrix | matrix, mixed_dates, trailing_spaces, typos |
| `zenith_pcr_ZB2624633.xlsx` | Zenith BioLabs | PCR | long | junk_sheets, multiline_cells, pending_states, scattered_meta |
| `copperfield_immuno_CF2648713.xlsx` | Copperfield Clinical | IMMUNO | long | blank_cols, combined_ref, operator_vals, thousands_sep, typos |
| `aldercreek_tumor_AC2699787.xlsx` | Alder Creek Labs | TUMOR | two_patient | header_offset, mixed_dates, two_patients, typos |
| `basalt_allergy_BD2622836.xlsx` | Basalt Diagnostics | ALLERGY | long | blank_rows, merged_headers, operator_vals, typos, unit_inline |

## Глоссарий quirks

- **header_offset** — шапка таблицы не в строке 1 (сверху логотип/текст)
- **merged_headers** — объединённые ячейки в над-заголовке
- **blank_rows** — случайные пустые строки внутри таблицы
- **blank_cols** — пустые колонки-разделители между полями
- **flag_inline** — флаг H/L внутри ячейки результата ('18.8 (H)')
- **color_only_flag** — аномалия помечена ТОЛЬКО цветом заливки, без текста
- **unit_inline** — единица измерения внутри ячейки результата
- **combined_ref** — референс внутри ячейки результата ('4.2 (3.5-5.0)')
- **unicode_units** — варианты/юникод единиц (µL, ³, mg/dl, K/uL, 10*3/uL)
- **comma_decimal** — запятая как десятичный разделитель (0,99)
- **thousands_sep** — разделители тысяч в числах (150,000)
- **num_as_text** — числа сохранены как текст, не как number
- **operator_vals** — значения с операторами ('<0.05', '>1000')
- **pending_states** — нечисловые статусы (PENDING/QNS/TNP/Cancelled)
- **typos** — опечатки в заголовках, аналитах, единицах, названиях листов
- **multiline_cells** — переносы строк внутри ячейки (\n)
- **trailing_spaces** — хвостовые/лишние пробелы в значениях
- **scattered_meta** — метаданные пациента разбросаны по разным ячейкам
- **footnote_rows** — строки-сноски вперемешку с данными
- **matrix** — транспонировано: атрибуты — строки, аналиты — столбцы
- **wide_format** — аналиты — заголовки столбцов, значения в одной строке
- **two_patients** — два пациента (батч) в одном файле
- **multi_table** — несколько под-таблиц с РАЗНЫМ порядком колонок
- **junk_sheets** — мусорные листы (READ ME, Notice, Index, пустые)
