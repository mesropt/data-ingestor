"""Gap-closure tests for the three holes 01-VERIFICATION.md found.

1. Excel tables never carried a column-locale annotation (PARSE-03 was
   satisfied for CSV only, though `helix_genomics_DE.xlsx` is the criterion's
   own reference fixture).
2. The CSV branch silently dropped `parse()`'s `hint` argument, so a human's
   answer to a decimal-locale question could never resolve it (PARSE-06).
3. The CLI had no way to supply a hint at all, so "proceed using the hint"
   was reachable only from Python — not from `assayingest <file>`.
"""

import json
from pathlib import Path

import pytest

from assayingest.cli import _hint_from_args, run
from assayingest.parsing.hint import NumericLocale, StructuralHint, StructureQuestion
from assayingest.parsing.table import RawTable, parse

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"


def _write_ambiguous_csv(tmp_path: Path) -> Path:
    """Every comma is followed by exactly 3 digits — thousands grouping and a
    3-decimal comma display are indistinguishable, so D-14 says ask."""
    csv = tmp_path / "ambiguous.csv"
    csv.write_text("Compound;Value\nA-1;1,234\nA-2;5,678\n", encoding="utf-8")
    return csv


# --- Gap 1: Excel tables must carry per-column locales -----------------------


def test_excel_table_carries_column_locales():
    table = parse(DATA / "helix_genomics_DE.xlsx")
    assert isinstance(table, RawTable)
    column = table.headers.index("Konz. (µM)")
    assert table.column_locales[column] == NumericLocale.DECIMAL_COMMA.value


def test_excel_locale_annotation_never_rewrites_the_value():
    """D-12: detection annotates, it does not convert. Phase 2 converts."""
    table = parse(DATA / "helix_genomics_DE.xlsx")
    column = table.headers.index("Konz. (µM)")
    assert table.rows[0][column] == "14,771"


def test_excel_column_locales_align_with_headers():
    table = parse(DATA / "meridian_cro_codes.xlsx")
    assert len(table.column_locales) == len(table.headers)


# --- Gap 2: the CSV branch must honour a hint --------------------------------


def test_csv_ambiguous_locale_still_asks_without_a_hint(tmp_path):
    outcome = parse(_write_ambiguous_csv(tmp_path))
    assert isinstance(outcome, StructureQuestion)
    assert "decimal locale" in outcome.unsure_about


def test_csv_hint_resolves_the_ambiguous_locale_question(tmp_path):
    csv = _write_ambiguous_csv(tmp_path)
    table = parse(csv, hint=StructuralHint(decimal_separator=","))
    assert isinstance(table, RawTable)
    assert table.column_locales[1] == NumericLocale.DECIMAL_COMMA.value
    assert table.rows[0][1] == "1,234"  # still a string, still as written


def test_csv_hint_can_choose_the_other_reading(tmp_path):
    """The human may answer 'those are thousands', not 'those are decimals'."""
    csv = _write_ambiguous_csv(tmp_path)
    table = parse(csv, hint=StructuralHint(decimal_separator="."))
    assert isinstance(table, RawTable)
    assert table.column_locales[1] == NumericLocale.DECIMAL_POINT.value


def test_csv_hint_forces_the_delimiter(tmp_path):
    csv = tmp_path / "piped.csv"
    csv.write_text("Compound|Target\nA-1|EGFR\n", encoding="utf-8")
    table = parse(csv, hint=StructuralHint(delimiter="|"))
    assert isinstance(table, RawTable)
    assert table.headers == ["Compound", "Target"]


def test_csv_hint_rejects_an_unusable_decimal_separator(tmp_path):
    """A broken hint is a broken input — that raises, unlike uncertainty (D-05)."""
    with pytest.raises(ValueError, match="decimal separator"):
        parse(_write_ambiguous_csv(tmp_path), hint=StructuralHint(decimal_separator=";"))


# --- Gap 3: the CLI must be able to carry a hint -----------------------------


def test_hint_from_args_returns_none_without_hints():
    assert _hint_from_args([]) is None


def test_hint_from_args_builds_every_supported_dimension():
    hint = _hint_from_args(
        ["header-row=4", "sheet=Week 1", "delimiter=;", "decimal=,"]
    )
    assert hint == StructuralHint(
        sheet_name="Week 1",
        header_row_index=4,
        delimiter=";",
        decimal_separator=",",
    )


def test_hint_from_args_rejects_an_unknown_key():
    with pytest.raises(ValueError, match="unknown structural hint"):
        _hint_from_args(["colour=blue"])


def test_hint_from_args_rejects_a_non_integer_header_row():
    with pytest.raises(ValueError, match="header-row"):
        _hint_from_args(["header-row=middle"])


def test_cli_without_a_hint_exits_structure_unresolved(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert run(str(_write_ambiguous_csv(tmp_path))) == 4


def test_cli_hint_resolves_the_structure_and_moves_on(tmp_path, monkeypatch):
    """Exit 3 means 'structure resolved, no credentials to map with' — the
    point is that it is no longer 4 ('structure unresolved')."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    csv = _write_ambiguous_csv(tmp_path)
    assert run(str(csv), hint=StructuralHint(decimal_separator=",")) == 3


def test_cli_question_tells_the_human_how_to_answer_it(tmp_path, capsys, monkeypatch):
    """A question nobody can answer is worse than no question at all."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    run(str(_write_ambiguous_csv(tmp_path)))
    assert "--hint decimal=," in capsys.readouterr().out


def test_question_wire_json_carries_answerability():
    """Phase 4's browser reads this JSON — it must know whether to offer a
    hint form at all, not just the CLI's text renderer (D-06, UI-02)."""
    question = parse(DATA / "apex_labs_wide_matrix.xlsx")
    payload = json.loads(json.dumps(question.to_dict()))
    assert payload["answerable_by_hint"] is False


def test_unsupported_shape_question_is_not_answerable_by_a_hint():
    """No hint un-pivots a wide matrix in v1 (PARSE-V2-01 is deferred), so the
    question must not advertise one."""
    question = parse(DATA / "apex_labs_wide_matrix.xlsx")
    assert isinstance(question, StructureQuestion)
    assert question.answerable_by_hint is False


def test_cli_never_offers_a_hint_that_would_not_help(capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    run(str(DATA / "apex_labs_wide_matrix.xlsx"))
    out = capsys.readouterr().out
    assert "To proceed, re-run with:" not in out
    assert "no structural hint resolves it" in out


def test_answerable_questions_still_offer_their_flags(capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    run(str(DATA / "zephyr_bio_ZB-2025.xlsx"))
    assert "To proceed, re-run with: --hint sheet=Week 1" in capsys.readouterr().out


def test_cli_hint_resolves_a_multi_sheet_workbook(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    workbook = str(DATA / "zephyr_bio_ZB-2025.xlsx")
    assert run(workbook) == 4  # three equally data-like sheets — asks
    assert run(workbook, hint=StructuralHint(sheet_name="Week 1")) == 3