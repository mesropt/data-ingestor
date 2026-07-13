"""`parse()` wires the CSV structural slice end-to-end: a clean table for a
resolvable file, a `StructureQuestion` (never a crash) for a genuinely
ambiguous one, and the CLI surfaces that question instead of guessing
(01-CONTEXT.md D-05, D-08, D-12, D-15)."""

from __future__ import annotations

from pathlib import Path

from assayingest.cli import run
from assayingest.parsing.hint import NumericLocale, StructureQuestion
from assayingest.parsing.table import RawTable, parse

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def _write_ambiguous_csv(tmp_path: Path) -> Path:
    """A fixture whose only numeric column is uniformly 3-digit-after-comma
    (indistinguishable from thousands grouping) — the D-14 ask case."""
    csv = tmp_path / "ambiguous_locale.csv"
    csv.write_text(
        "Compound,Value,Target\n"
        'CPD-1,"1,234",EGFR\n'
        'CPD-2,"5,678",JAK2\n'
        'CPD-3,"9,012",BRAF\n'
    )
    return csv


def test_parse_pinnacle_returns_clean_table_with_decimal_comma_annotated():
    outcome = parse(DATA / "pinnacle_labs_export.csv")
    assert isinstance(outcome, RawTable)
    assert outcome.headers == [
        "Compound",
        "Endpoint",
        "Value",
        "Unit",
        "Target",
        "Replicates",
        "Date",
    ]
    assert outcome.row_count == 14
    value_index = outcome.headers.index("Value")
    assert outcome.column_locales[value_index] == NumericLocale.DECIMAL_COMMA.value


def test_parse_pinnacle_never_asks_a_question():
    outcome = parse(DATA / "pinnacle_labs_export.csv")
    assert not isinstance(outcome, StructureQuestion)


def test_parse_does_not_rewrite_cell_values_to_numbers():
    outcome = parse(DATA / "pinnacle_labs_export.csv")
    value_index = outcome.headers.index("Value")
    assert outcome.rows[0][value_index] == "11,076"  # still a string, verbatim


def test_parse_ambiguous_locale_returns_structure_question_not_raw_table(tmp_path):
    outcome = parse(_write_ambiguous_csv(tmp_path))
    assert isinstance(outcome, StructureQuestion)
    assert "decimal" in outcome.unsure_about.lower() or "locale" in outcome.unsure_about.lower()


def test_parse_ambiguous_locale_does_not_raise(tmp_path):
    # D-05: structural uncertainty is a RETURNED value, never an exception.
    result = parse(_write_ambiguous_csv(tmp_path))
    assert result is not None


def test_parse_missing_file_still_raises_filenotfound():
    import pytest

    with pytest.raises(FileNotFoundError):
        parse(DATA / "does_not_exist.csv")


def test_cli_ask_branch_prints_question_and_does_not_crash(tmp_path, capsys):
    csv = _write_ambiguous_csv(tmp_path)
    exit_code = run(str(csv))
    out = capsys.readouterr().out
    assert exit_code not in (0,)  # never silently "succeeds"
    assert "unsure" in out.lower() or "question" in out.lower()


def test_cli_ask_branch_does_not_require_credentials(tmp_path, monkeypatch, capsys):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    csv = _write_ambiguous_csv(tmp_path)
    exit_code = run(str(csv))
    out = capsys.readouterr().out
    # The ask-branch must fire before the credentials gate — asking is the
    # deterministic layer's job and needs no API key (D-04/D-08).
    assert "credentials" not in out.lower()
    assert exit_code != 0


def test_parse_helixbio_returns_raw_table_with_hash_header_intact():
    # Regression: the live parse() path (used by /api/upload) must not
    # truncate the '# Reps' header column and shift every row.
    outcome = parse(DATA / "helixbio_export.csv")
    assert isinstance(outcome, RawTable)
    assert outcome.headers == [
        "Compound Name",
        "Endpoint",
        "Conc (uM)",
        "Gene Symbol",
        "# Reps",
        "Experiment Date",
    ]


def test_parse_helixbio_first_row_has_compound_id_intact():
    outcome = parse(DATA / "helixbio_export.csv")
    assert outcome.rows[0] == [
        "HLX-100",
        "EC50",
        "0.045",
        "EGFR",
        "3",
        "03/11/2025",
    ]
