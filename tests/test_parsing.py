"""The parser must surface the mess (blank headers, stray spaces) faithfully."""

from pathlib import Path

import pytest

from assayingest.parsing.table import parse_file

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def test_parses_headers_and_rows():
    table = parse_file(DATA / "helixbio_export.csv")
    assert table.headers[0] == "Compound Name"
    assert table.row_count == 12  # data rows in the fixture
    assert table.rows[0][0] == "HLX-100"


def test_blank_header_is_preserved_as_empty_string():
    # NovaScreen ships its unit column with no name — the mapper must see it.
    table = parse_file(DATA / "novascreen_batch01.csv")
    assert table.headers == ["cmpd", "assay", "potency", "", "target_gene",
                             "replicates", "date"]


def test_leading_space_in_header_is_stripped():
    # Crestchem's " ID" column has a leading space that must be cleaned.
    table = parse_file(DATA / "crestchem_results.csv")
    assert table.headers[0] == "ID"


def test_values_are_kept_verbatim_as_strings():
    # Ambiguous dates must not be coerced by pandas — the curator resolves them.
    table = parse_file(DATA / "helixbio_export.csv")
    date_col = table.headers.index("Experiment Date")
    assert table.rows[0][date_col] == "03/11/2025"


def test_sample_limits_rows():
    table = parse_file(DATA / "novascreen_batch01.csv")
    assert len(table.sample(2)) == 2


def test_missing_file_raises_filenotfound():
    with pytest.raises(FileNotFoundError):
        parse_file(DATA / "does_not_exist.csv")


def test_unsupported_extension_raises_valueerror(tmp_path):
    junk = tmp_path / "notes.txt"
    junk.write_text("hello")
    with pytest.raises(ValueError, match="csv or .xlsx"):
        parse_file(junk)