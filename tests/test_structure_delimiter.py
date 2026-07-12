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


def test_helixbio_hash_header_column_survives():
    # Regression: pandas' comment="#" kwarg truncates ANY line at the first
    # '#', even a header row that is not a comment at all.
    headers, _ = read_csv_grid(DATA / "helixbio_export.csv")
    assert headers == [
        "Compound Name",
        "Endpoint",
        "Conc (uM)",
        "Gene Symbol",
        "# Reps",
        "Experiment Date",
    ]


def test_helixbio_compound_id_survives_in_first_row():
    _, rows = read_csv_grid(DATA / "helixbio_export.csv")
    assert rows[0] == ["HLX-100", "EC50", "0.045", "EGFR", "3", "03/11/2025"]


def test_hash_mid_line_in_data_cell_survives_verbatim(tmp_path):
    csv_path = tmp_path / "lot_hash.csv"
    csv_path.write_text("A,B,C\n1,Lot #42,3\n")
    headers, rows = read_csv_grid(csv_path)
    assert headers == ["A", "B", "C"]
    assert rows[0] == ["1", "Lot #42", "3"]


def test_leading_prose_comment_line_is_still_dropped(tmp_path):
    csv_path = tmp_path / "prose_comment.csv"
    csv_path.write_text("# exported by lab\nA,B,C\n1,2,3\n")
    headers, rows = read_csv_grid(csv_path)
    assert headers == ["A", "B", "C"]
    assert rows == [["1", "2", "3"]]


def test_hash_prefixed_header_row_is_refused(tmp_path):
    # D-01: a '#'-prefixed line that is structurally a header/data row (same
    # field count as the table) must never be silently dropped — it is
    # ambiguous whether it's a comment or a real header, so fail closed.
    csv_path = tmp_path / "hash_header.csv"
    csv_path.write_text("# ID,Value,Target\nA,1,EGFR\nB,2,JAK2\n")
    with pytest.raises(ValueError, match=r"(?i)column|header"):
        read_csv_grid(csv_path)


def test_hash_inside_open_multiline_quoted_field_survives(tmp_path):
    csv_path = tmp_path / "quoted_multiline_hash.csv"
    csv_path.write_text(
        'A,B,C\n1,"line one\n#not a comment\nline three",3\n'
    )
    headers, rows = read_csv_grid(csv_path)
    assert headers == ["A", "B", "C"]
    assert rows == [["1", "line one\n#not a comment\nline three", "3"]]


def test_empty_file_raises_valueerror_matching_empty(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("")
    with pytest.raises(ValueError, match=r"(?i)empty"):
        read_csv_grid(csv_path)


def test_non_utf8_bytes_raise_valueerror_matching_utf8(tmp_path):
    csv_path = tmp_path / "bad_encoding.csv"
    csv_path.write_bytes(b"A,B\n\xcb\xf2,2\n")
    with pytest.raises(ValueError, match=r"(?i)UTF-8"):
        read_csv_grid(csv_path)


def test_comments_only_file_raises_valueerror_matching_empty(tmp_path):
    csv_path = tmp_path / "comments_only.csv"
    csv_path.write_text("# only a comment\n# another comment\n")
    with pytest.raises(ValueError, match=r"(?i)empty"):
        read_csv_grid(csv_path)
