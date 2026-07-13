"""End-to-end `run()` exit codes, plus a live mapper check gated behind an
explicit ASSAYINGEST_LIVE_TESTS=1 opt-in (never merely "a key is present" --
an auto-loaded .env means a key can be present with no intent to spend
money, so intent is what gates the call, not credential presence)."""

import os
from pathlib import Path

import pytest
from openpyxl import Workbook

from assayingest import cli
from assayingest.cli import run
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.loader import load as load_field_set
from assayingest.fields.models import Field, FieldSet
from assayingest.mapping.mapper import propose_mapping
from assayingest.parsing.hint import StructuralHint
from assayingest.parsing.structure.layout import LayoutKind, SheetLayout
from assayingest.parsing.table import RawTable, parse, parse_file

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"
PRESET = Path(__file__).resolve().parent.parent / "presets" / "assay-potency.yaml"
_CASCADE = DATA / "lab_corpus" / "cascade_allergy_CS-2026-698392.xlsx"


def test_run_reports_missing_file(capsys):
    assert run(str(DATA / "missing.csv")) == 2
    assert "no file" in capsys.readouterr().err


def test_run_reports_missing_credentials(monkeypatch, capsys):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    assert run(str(DATA / "novascreen_batch01.csv")) == 3
    assert "credentials" in capsys.readouterr().err


# --- D-23 exit-code gate, exercised offline with a monkeypatched mapper -----


def _blocked_proposal() -> MappingProposal:
    return MappingProposal(
        source_columns=["a"],
        field_mappings=[
            FieldMapping(
                target_field="value",
                source_column=None,
                confidence=0.5,
                reasoning="ambiguous column",
                needs_confirmation=True,
            )
        ],
    )


def _ready_proposal() -> MappingProposal:
    return MappingProposal(
        source_columns=["a"],
        field_mappings=[
            FieldMapping(
                target_field="value",
                source_column="a",
                confidence=1.0,
                reasoning="exact match",
                needs_confirmation=False,
            )
        ],
    )


def test_map_one_exits_5_when_the_proposal_is_blocked(monkeypatch):
    monkeypatch.setattr(
        cli, "propose_mapping", lambda table, field_set, client=None, **kwargs: _blocked_proposal()
    )
    # `_map_one`'s credential check now lives on the no-profile branch
    # (Pitfall 3) -- with no `store` this always takes that branch, so it
    # needs a (fake) key even though `propose_mapping` is monkeypatched.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    table = parse_file(DATA / "novascreen_batch01.csv")
    # WR-03: field_set=None + credentials now raises before reaching the
    # (monkeypatched) mapper at all -- a real minimal field_set is required
    # to exercise the D-23 exit-code gate this test targets.
    field_set = FieldSet(fields=(Field(name="value"),))
    assert cli._map_one(table, field_set=field_set) == 5


def test_map_one_exits_0_only_when_the_proposal_is_ready(monkeypatch):
    monkeypatch.setattr(
        cli, "propose_mapping", lambda table, field_set, client=None, **kwargs: _ready_proposal()
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    table = parse_file(DATA / "novascreen_batch01.csv")
    field_set = FieldSet(fields=(Field(name="value"),))
    assert cli._map_one(table, field_set=field_set) == 0


# --- WR-03: field_set=None + credentials must not crash with AttributeError -


def test_resolve_proposal_raises_value_error_when_field_set_is_none_with_credentials(
    monkeypatch,
):
    """`run()`/`_resolve_proposal` accept `field_set=None` for early-exit
    callers, but if credentials ARE configured, the fresh-Claude branch used
    to dereference `field_set.fields` with no guard -- a bare
    `AttributeError` instead of a consequence-naming error `_map_one` can
    catch and report cleanly."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    table = parse_file(DATA / "novascreen_batch01.csv")

    with pytest.raises(ValueError, match="no field set"):
        cli._resolve_proposal(table, None, None)


def test_map_one_reports_a_clean_exit_1_when_field_set_is_none_with_credentials(
    monkeypatch, capsys
):
    """The same hazard exercised through `_map_one`: it must already catch
    `ValueError` and exit 1, never propagate a bare traceback."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    table = parse_file(DATA / "novascreen_batch01.csv")

    assert cli._map_one(table, field_set=None, store=None) == 1
    assert "no field set" in capsys.readouterr().err


@pytest.mark.skipif(
    os.environ.get("ASSAYINGEST_LIVE_TESTS") != "1",
    reason="live mapper test costs real money -- opt in with ASSAYINGEST_LIVE_TESTS=1",
)
def test_mapper_flags_missing_unit_on_novascreen():
    # The money shot: NovaScreen's first file has no unit column, so the mapper
    # must infer nM from the value range and flag it for confirmation.
    field_set = load_field_set(PRESET)
    table = parse_file(DATA / "novascreen_batch01.csv")
    proposal = propose_mapping(table, field_set)

    assert {m.target_field for m in proposal.field_mappings} == set(
        field_set.field_names
    )
    unit = next(m for m in proposal.field_mappings if m.target_field == "unit")
    assert unit.needs_confirmation
    assert not proposal.is_ready


# --- 12-09 Task 2: the CLI's layout judge (SHAPE-01, D-12-05/D-12-16) -------------
#
# 12-RESEARCH's four-path table promised the CLI "the judge, or nothing", and
# only the "nothing" half was planned. Once the heuristic classifier is gone
# (Wave C), a CLI with no verdict source would hand back a layout question for
# EVERY .xlsx -- credentials or not, including every ordinary row-per-record
# file in data/synthetic/. This is the judge half.
#
# The judge is credentials-gated exactly as the mapper call is: with a key, a
# real verdict; without one, no client is ever constructed and the tool asks
# the answerable layout question rather than guessing. A judge that FAILS is
# not a crash -- it degrades to exactly the same honest "no verdict in hand".
#
# Every test here is OFFLINE: the judge is injected at `cli.judge_workbook_layout`,
# the same module-level seam `cli.propose_mapping` already uses. tests/conftest.py
# refuses the real judge by default, so no test can reach the network merely by
# setting a fake API key.


def _row_verdict(**kwargs) -> SheetLayout:
    return SheetLayout(
        kind=LayoutKind.ROW_PER_RECORD,
        confidence=0.97,
        reasoning="an ordinary table",
        **kwargs,
    )


def _judge_returning(verdicts: dict[str, SheetLayout]):
    """A judge fake in `judge_workbook_layout`'s exact shape, recording what it
    was sent -- so a test can assert on `headers_only` as well as the verdict."""
    calls: list[dict] = []

    def _judge(grids, *, headers_only):
        calls.append({"sheets": list(grids), "headers_only": headers_only})
        return {name: verdicts[name] for name in grids if name in verdicts}

    return _judge, calls


def _refusing_judge(calls: list):
    def _judge(grids, *, headers_only):
        calls.append(grids)
        raise AssertionError("the judge must not be called on this path")

    return _judge


def _classifier_refused_workbook(tmp_path: Path) -> Path:
    """A real 3-row table, a blank separator, then trailing prose. The heuristic
    calls this `multiple_tables` and REFUSES it outright, so the CLI cannot read
    it today at all -- which is what makes the with-judge test below non-vacuous:
    only a verdict can produce this table."""
    workbook = Workbook()
    worksheet = workbook.active
    for row in (
        ("Compound", "Assay", "Result", "Unit", "Target", "Replicates", "Date"),
        ("A-1", "IC50", 12.5, "nM", "EGFR", 3, "2026-01-05"),
        ("A-2", "IC50", 44.0, "nM", "EGFR", 3, "2026-01-06"),
        ("A-3", "IC50", 91.2, "nM", "EGFR", 3, "2026-01-07"),
        (None, None, None, None, None, None, None),
        ("Reviewed by J. Chen, 2026-05-04", None, None, None, None, None, None),
    ):
        worksheet.append(row)
    path = tmp_path / "refused_assays.xlsx"
    workbook.save(path)
    return path


def _ready_potency_mapping(table: RawTable, field_set, client=None, **kwargs):
    return MappingProposal(
        source_columns=table.headers,
        field_mappings=[
            FieldMapping(
                target_field=name,
                source_column=table.headers[index],
                confidence=1.0,
                reasoning="exact match",
                needs_confirmation=False,
            )
            for index, name in enumerate(field_set.field_names)
        ],
    )


def test_the_cli_judge_reads_a_file_the_tool_could_not_read_before(
    tmp_path, monkeypatch, capsys, profile_store
):
    """The B2 test: with credentials, the CLI HAS a verdict source. The verdict's
    row range trims the trailing prose, and a grid the tool refuses outright
    today comes back as a mapped draft.

    Non-vacuous by construction: without the judge this file is `multiple_tables`
    and exits 4."""
    path = _classifier_refused_workbook(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert run(str(path), field_set=load_field_set(PRESET), store=profile_store) == 4
    capsys.readouterr()

    judge, calls = _judge_returning(
        {"Sheet": _row_verdict(header_row_index=0, first_data_row=1, last_data_row=3)}
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(cli, "judge_workbook_layout", judge)
    monkeypatch.setattr(cli, "propose_mapping", _ready_potency_mapping)

    exit_code = run(str(path), field_set=load_field_set(PRESET), store=profile_store)

    out = capsys.readouterr().out
    assert exit_code == 0, "a judged, fully-clear file must ingest"
    assert "BLOCKED: structure unresolved" not in out
    assert len(calls) == 1, "one judge call, for the one target sheet"
    assert "Reviewed by J. Chen" not in out, "the verdict's row range trims the prose"


def test_without_credentials_the_cli_asks_instead_of_judging_or_guessing(
    monkeypatch, capsys, profile_store
):
    """The fail-closed half, and the path most of the suite runs on: no key means
    NO judge -- no client is constructed and none is called -- and the tool asks
    the answerable structural question rather than guessing at the layout."""
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    calls: list = []
    monkeypatch.setattr(cli, "judge_workbook_layout", _refusing_judge(calls))

    exit_code = run(
        str(_CASCADE),
        sheet="Patient Info",
        field_set=load_field_set(PRESET),
        store=profile_store,
    )

    out = capsys.readouterr().out
    assert exit_code == 4, "the structural-question exit code, never a guessed table"
    assert "BLOCKED: structure unresolved" in out
    assert calls == [], "no credentials means the judge is never reached at all"


def test_a_failing_judge_degrades_to_the_question_never_a_crash(
    tmp_path, monkeypatch, capsys, profile_store
):
    """A judge that raises -- an auth error, an API error, a malformed response --
    lands the human on exactly the same honest answer as no judge at all. It is
    an availability boundary, not a new failure mode: no traceback, no crash, no
    guessed table."""
    path = _classifier_refused_workbook(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(cli, "propose_mapping", _ready_potency_mapping)

    for boom in (
        lambda grids, *, headers_only: (_ for _ in ()).throw(ValueError("malformed")),
        lambda grids, *, headers_only: (_ for _ in ()).throw(RuntimeError("network")),
    ):
        monkeypatch.setattr(cli, "judge_workbook_layout", boom)

        exit_code = run(
            str(path), field_set=load_field_set(PRESET), store=profile_store
        )

        out = capsys.readouterr().out
        assert exit_code == 4
        assert "BLOCKED: structure unresolved" in out


def test_an_ordinary_row_per_record_file_still_ingests_under_the_judge(
    monkeypatch, capsys, profile_store
):
    """SC5 at the CLI, in one file: a confident `row_per_record` verdict means
    "read it the ordinary way" and changes nothing -- zephyr's Week 1 comes back
    byte-for-byte the table it is today, with no question raised.

    This pins the null hypothesis (D-12-15) at the CLI. It passes today through
    the classifier and after Wave C through the verdict; the full sweep over
    every such file lives in tests/test_sc5_row_per_record_parity.py.

    The exit code is deliberately NOT asserted as 0: zephyr's `Units` column
    carries an ASCII `uM`, which the validator honestly flags (exit 5 — mapped,
    one field to confirm). What this test is about is that the file INGESTED —
    a real table was read and mapped — never that it was structurally refused."""
    today = parse(DATA / "zephyr_bio_ZB-2025.xlsx", sheet="Week 1")
    assert isinstance(today, RawTable)

    judge, calls = _judge_returning({"Week 1": _row_verdict(header_row_index=4)})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(cli, "judge_workbook_layout", judge)
    monkeypatch.setattr(cli, "propose_mapping", _ready_potency_mapping)

    exit_code = run(
        str(DATA / "zephyr_bio_ZB-2025.xlsx"),
        sheet="Week 1",
        field_set=load_field_set(PRESET),
        store=profile_store,
    )

    out = capsys.readouterr().out
    assert exit_code != 4, "a judged row_per_record file must never be refused"
    assert "BLOCKED: structure unresolved" not in out
    assert "Proposed mapping" in out, "it reached the mapper — it really ingested"
    assert calls[0]["sheets"] == ["Week 1"], "only the one honest target sheet"
    for header in today.headers:
        assert header in out


def test_the_clis_judge_honours_headers_only(
    tmp_path, monkeypatch, capsys, profile_store
):
    """SHAPE-04 / T-12-30 at the CLI's NEW send site. D-12-06: the privacy
    guarantee has no choke point -- every Claude call site re-implements it, and
    this phase adds one. The judge still RUNS in private mode (D-12-05: skipping
    it would leave the private mode with no judge at all), with the grid redacted
    to cell types by `render_evidence_grid`'s required `headers_only` kwarg."""
    path = _classifier_refused_workbook(tmp_path)
    judge, calls = _judge_returning(
        {"Sheet": _row_verdict(header_row_index=0, first_data_row=1, last_data_row=3)}
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(cli, "judge_workbook_layout", judge)
    monkeypatch.setattr(cli, "propose_mapping", _ready_potency_mapping)

    run(
        str(path),
        field_set=load_field_set(PRESET),
        store=profile_store,
        headers_only=True,
    )
    capsys.readouterr()

    assert calls[0]["headers_only"] is True, (
        "the curator's headers-only toggle must reach the judge, or the "
        "feature is a lie (D-12-11)"
    )

    run(str(path), field_set=load_field_set(PRESET), store=profile_store)
    assert calls[1]["headers_only"] is False, (
        "and the DEFAULT path still sends the real grid (D-12-09) -- realness "
        "is a requirement there, not an accident"
    )


def test_the_cli_never_second_guesses_a_human_who_named_the_header_row(
    tmp_path, monkeypatch, capsys, profile_store
):
    """D-02/PARSE-06: a human's own answer is never second-guessed. An explicit
    `--hint header-row=N` IS the layout answer (12-09's promotion rule), so the
    judge is not consulted at all -- it cannot be spent, and, far more
    importantly, it cannot overrule the human with a verdict of its own (a
    `key_value` verdict here would bounce the curator's own answer back at them
    as a question).

    The file resolves on the human's answer alone: no structural refusal, and
    the mapper is reached. (Exit is 5, not 0: a bare header row names no data
    range, so the trailing prose row is read too and the validator honestly
    flags it -- which is the ordinary way, exactly as asked for.)"""
    path = _classifier_refused_workbook(tmp_path)
    calls: list = []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(cli, "judge_workbook_layout", _refusing_judge(calls))
    monkeypatch.setattr(cli, "propose_mapping", _ready_potency_mapping)

    exit_code = run(
        str(path),
        hint=StructuralHint(header_row_index=0),
        field_set=load_field_set(PRESET),
        store=profile_store,
    )

    out = capsys.readouterr().out
    assert exit_code != 4, "the human's answer resolves the file on its own"
    assert "BLOCKED: structure unresolved" not in out
    assert "Proposed mapping" in out
    assert calls == [], "an answered layout question is never re-judged"


@pytest.mark.skipif(
    os.environ.get("ASSAYINGEST_LIVE_TESTS") != "1",
    reason="live mapper test costs real money -- opt in with ASSAYINGEST_LIVE_TESTS=1",
)
def test_run_exits_5_on_a_blocked_proposal(profile_store):
    # D-23: a proposed-but-not-ready mapping is exit 5, never a silent 0.
    # The store is injected even though this test is normally skipped: without it,
    # `run()` would open a session on the composition root -- i.e. the DEV database.
    field_set = load_field_set(PRESET)
    exit_code = run(
        str(DATA / "novascreen_batch01.csv"), field_set=field_set, store=profile_store
    )
    assert exit_code == 5
