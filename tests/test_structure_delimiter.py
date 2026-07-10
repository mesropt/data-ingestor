"""CSV delimiter + comment-line sniffing must survive the pinnacle fixture's
`delimiter=';'` comment-line trap (01-RESEARCH.md Pattern 2, Pitfall 1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from assayingest.parsing.structure.delimiter import read_csv_grid

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def test_pinnacle_csv_reads_seven_headers_not_one_junk_column():
    headers, rows = read_csv_grid(DATA / "pinnacle_labs_export.csv")
    assert headers == [
        "Compound",
        "Endpoint",
        "Value",
        "Unit",
        "Target",
        "Replicates",
        "Date",
    ]
    assert len(rows) == 14


def test_pinnacle_csv_ignores_the_comment_lines_delimiter_hint():
    # A naive csv.Sniffer() picks '=' out of the "delimiter=';'" comment text.
    headers, _ = read_csv_grid(DATA / "pinnacle_labs_export.csv")
    assert len(headers) == 7
    assert all("=" not in h for h in headers)


def test_pinnacle_first_data_row_values():
    _, rows = read_csv_grid(DATA / "pinnacle_labs_export.csv")
    assert rows[0] == ["PIN-010", "IC50", "11,076", "uM", "EGFR", "3", "01/01/2025"]


def test_missing_file_raises_filenotfound():
    with pytest.raises(FileNotFoundError):
        read_csv_grid(DATA / "does_not_exist.csv")


def test_non_csv_extension_raises_valueerror(tmp_path):
    junk = tmp_path / "notes.txt"
    junk.write_text("hello")
    with pytest.raises(ValueError, match=r"\.csv"):
        read_csv_grid(junk)


def test_delimiter_module_imports_no_anthropic():
    source = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "assayingest"
        / "parsing"
        / "structure"
        / "delimiter.py"
    )
    text = source.read_text()
    import_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    assert not any("anthropic" in line for line in import_lines)
