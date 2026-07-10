"""Column-level decimal-locale classification — variance across a column
proves a decimal separator; uniformity is ambiguous, never guessed
(01-CONTEXT.md D-13/D-14, 01-RESEARCH.md Pattern 3)."""

from __future__ import annotations

from pathlib import Path

from assayingest.parsing.hint import NumericLocale
from assayingest.parsing.structure.delimiter import read_csv_grid
from assayingest.parsing.structure.locale import annotate_columns, classify_column

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def test_pinnacle_value_sample_resolves_decimal_comma_without_ambiguity():
    result = classify_column(["11,076", "446,2", "654,85", "6,197"])
    assert result == NumericLocale.DECIMAL_COMMA


def test_helix_konz_sample_resolves_decimal_comma():
    result = classify_column(["14,771", "19,488", "30,16", "3,338"])
    assert result == NumericLocale.DECIMAL_COMMA


def test_uniform_three_digit_comma_groups_are_ambiguous():
    result = classify_column(["1,234", "5,678", "9,012"])
    assert result == NumericLocale.AMBIGUOUS


def test_single_three_digit_comma_value_cannot_self_disambiguate():
    result = classify_column(["1,234"])
    assert result == NumericLocale.AMBIGUOUS


def test_thousands_dot_with_comma_decimal_only_last_group_matters():
    result = classify_column(["1.234,56", "2.345,67"])
    assert result == NumericLocale.DECIMAL_COMMA


def test_mixed_dot_decimal_and_comma_three_digit_is_ambiguous():
    result = classify_column(["1.5", "1,234"])
    assert result == NumericLocale.AMBIGUOUS


def test_non_numeric_column():
    result = classify_column(["EGFR", "JAK2"])
    assert result == NumericLocale.NON_NUMERIC


def test_annotate_columns_returns_one_locale_per_column_for_pinnacle():
    headers, rows = read_csv_grid(DATA / "pinnacle_labs_export.csv")
    locales = annotate_columns(headers, rows)
    assert len(locales) == len(headers)
    assert locales[headers.index("Value")] == NumericLocale.DECIMAL_COMMA


def test_locale_module_imports_no_anthropic():
    source = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "assayingest"
        / "parsing"
        / "structure"
        / "locale.py"
    )
    text = source.read_text()
    import_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    assert not any("anthropic" in line for line in import_lines)
