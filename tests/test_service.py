"""service.py -- the CLI-and-API orchestration seam (04-01, TDD RED).

Proves the extracted decision logic decides but never renders: nothing is
printed, typed exceptions replace the old sentinel-tuple/print-then-exit
idioms, and the auto-apply path never constructs an Anthropic client or
checks credentials. Written test-first per the plan's TDD gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from assayingest import service
from assayingest.domain.models import ColumnCandidate, FieldMapping, MappingProposal
from assayingest.fields.models import Field, FieldSet
from assayingest.learning.profile import LearnedProfile
from assayingest.learning.reconstruct import stored_mapping_from
from assayingest.learning.signature import column_signature
from assayingest.parsing.hint import StructureQuestion
from assayingest.parsing.table import RawTable, parse_file

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"
NOVASCREEN_01 = DATA / "novascreen_batch01.csv"


def _field_set() -> FieldSet:
    """No declared constraints on any field -- validate() inside
    resolve_or_map() then contributes only a validator_note, never changes
    needs_confirmation, so "equals what propose_mapping produced" is
    provable field-by-field without fighting VAL-03's explicit-absence note.
    """
    return FieldSet(fields=(Field(name="compound_id"), Field(name="value")))


def _ready_proposal(headers: list[str]) -> MappingProposal:
    return MappingProposal(
        source_columns=headers,
        field_mappings=[
            FieldMapping(
                target_field="compound_id",
                source_column="cmpd",
                confidence=1.0,
                reasoning="exact match",
                needs_confirmation=False,
            ),
            FieldMapping(
                target_field="value",
                source_column="potency",
                confidence=1.0,
                reasoning="exact match",
                needs_confirmation=False,
            ),
        ],
    )


# --- MapResult / resolve_or_map: decides, never renders ---------------------


def test_resolve_or_map_returns_mapresult_matching_the_monkeypatched_mapper(
    monkeypatch, capsys
):
    field_set = _field_set()
    table = parse_file(NOVASCREEN_01)

    monkeypatch.setattr(
        service, "propose_mapping",
        lambda t, fs, client=None, **kwargs: _ready_proposal(t.headers),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    result = service.resolve_or_map(str(NOVASCREEN_01), field_set, store=None)

    assert isinstance(result, service.MapResult)
    assert result.provenance == "fresh-claude"
    assert result.table.headers == table.headers
    resolved = {m.target_field: m.source_column for m in result.proposal.field_mappings}
    assert resolved == {"compound_id": "cmpd", "value": "potency"}
    assert all(not m.needs_confirmation for m in result.proposal.field_mappings)
    assert capsys.readouterr().out == ""


def test_resolve_or_map_auto_applies_from_a_matching_profile_with_no_mapper_call(tmp_path, monkeypatch, capsys, profile_store):
    field_set = _field_set()
    table = parse_file(NOVASCREEN_01)
    db_path = tmp_path / "profiles.db"
    store = profile_store
    profile = LearnedProfile(
        profile_id="profile-1",
        field_set_signature=field_set.signature,
        column_signature=column_signature(table.headers),
        field_mappings=tuple(
            stored_mapping_from(m, table.headers)
            for m in _ready_proposal(table.headers).field_mappings
        ),
        structural_hint=None,
        created_at="2026-01-01T00:00:00+00:00",
    )
    store.save(profile)

    called = {"n": 0}

    def _spy(*args, **kwargs):
        called["n"] += 1
        return _ready_proposal(table.headers)

    monkeypatch.setattr(service, "propose_mapping", _spy)
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    result = service.resolve_or_map(str(NOVASCREEN_01), field_set, store=store)

    assert isinstance(result, service.MapResult)
    assert result.provenance == "auto-applied-from-profile"
    assert result.profile_id == "profile-1"
    assert called["n"] == 0
    assert capsys.readouterr().out == ""


def test_resolve_or_map_returns_the_structural_question_unchanged(monkeypatch, capsys):
    question = StructureQuestion(
        unsure_about="which row is the real header",
        reason="ambiguous",
        confidence=0.4,
    )
    monkeypatch.setattr(
        service, "parse", lambda path, *, sheet=None, hint=None: question
    )

    result = service.resolve_or_map("whatever.csv", _field_set(), store=None)

    assert result is question
    assert capsys.readouterr().out == ""


def test_resolve_or_map_raises_missing_credentials_error_on_the_miss_branch(
    monkeypatch,
):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("propose_mapping must never be called: no credentials")

    monkeypatch.setattr(service, "propose_mapping", _fail_if_called)

    with pytest.raises(service.MissingCredentialsError):
        service.resolve_or_map(str(NOVASCREEN_01), _field_set(), store=None)


def test_resolve_or_map_raises_value_error_when_field_set_is_none_with_credentials(
    monkeypatch,
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with pytest.raises(ValueError, match="no field set"):
        service.resolve_or_map(str(NOVASCREEN_01), None, store=None)


# --- confirm(): the P1 server-side gate --------------------------------------


def _table() -> RawTable:
    return RawTable(
        headers=["cmpd", "potency"],
        rows=[["NVS-1", "12.5"], ["NVS-2", "8.0"]],
        source_name="batch.csv",
    )


def test_confirm_returns_a_confirmresult_for_a_fully_clear_mapping():
    table = _table()
    field_set = _field_set()
    edited = _ready_proposal(table.headers).field_mappings

    result = service.confirm(table, edited, field_set)

    assert isinstance(result, service.ConfirmResult)
    assert result.proposal.is_ready is True
    assert result.tidy.field_names == ["compound_id", "value"]
    assert result.manifest["provenance"] == "fresh-claude"


def test_confirm_never_trusts_a_client_claimed_ready_flag():
    """A tampered `needs_confirmation=False` sent by the client must not
    survive re-validation -- is_ready is recomputed on the freshly-built
    proposal, never read off the input (P1)."""
    table = _table()
    field_set = FieldSet(fields=(Field(name="value", min=100),))
    edited = [
        FieldMapping(
            target_field="value",
            source_column="potency",
            confidence=1.0,
            reasoning="curator says so",
            needs_confirmation=False,  # tampered/stale claim
        )
    ]

    with pytest.raises(service.NotReadyError) as excinfo:
        service.confirm(table, edited, field_set)

    assert "value" in str(excinfo.value)


def test_confirm_raises_not_ready_error_listing_unclear_fields():
    table = _table()
    field_set = _field_set()
    blocked = [
        FieldMapping(
            target_field="compound_id",
            source_column=None,
            confidence=0.4,
            reasoning="ambiguous",
            needs_confirmation=True,
        ),
        FieldMapping(
            target_field="value",
            source_column="potency",
            confidence=1.0,
            reasoning="exact match",
            needs_confirmation=False,
        ),
    ]

    with pytest.raises(service.NotReadyError) as excinfo:
        service.confirm(table, blocked, field_set)

    assert [m.target_field for m in excinfo.value.unclear_fields] == ["compound_id"]


def test_confirm_save_profile_persists_exactly_one_learned_profile(profile_store):
    table = _table()
    field_set = _field_set()
    edited = _ready_proposal(table.headers).field_mappings
    store = profile_store

    result = service.confirm(table, edited, field_set, save_profile=True, store=store)

    assert result.profile_id is not None
    found = store.find(field_set.signature, column_signature(table.headers))
    assert found is not None
    assert found.profile_id == result.profile_id


def test_confirm_with_save_profile_true_still_blocks_on_yellow(profile_store):
    table = _table()
    field_set = _field_set()
    blocked = [
        FieldMapping(
            target_field="compound_id", source_column=None, confidence=0.4,
            reasoning="ambiguous", needs_confirmation=True,
        ),
        FieldMapping(
            target_field="value", source_column="potency", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
    ]
    store = profile_store

    with pytest.raises(service.NotReadyError):
        service.confirm(table, blocked, field_set, save_profile=True, store=store)

    assert store.find(field_set.signature, column_signature(table.headers)) is None


# --- the confirm gate judges only what reaches the export (VAL-02 scoping) ---


def _unit_field_set() -> FieldSet:
    return FieldSet(
        fields=(
            Field(name="compound_id"),
            Field(name="unit", type="text", allowed_values=("µM", "nM", "%"), required=False),
        )
    )


def test_confirm_passes_when_only_a_rejected_alternative_violates_allowed_values():
    """The Review-screen dead end: the file has no unit column, the human
    accepted the inferred 'nM', and Claude's low-ranked alternative names a
    numeric column that violates allowed_values. The alternative is a
    rejected suggestion nothing in the export reads -- the gate must pass,
    not raise NotReadyError forever."""
    table = _table()
    field_set = _unit_field_set()
    edited = [
        FieldMapping(
            target_field="compound_id", source_column="cmpd", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        FieldMapping(
            target_field="unit", source_column=None, confidence=0.55,
            reasoning="inferred from value magnitude", needs_confirmation=False,
            inferred_value="nM",
            alternatives=[ColumnCandidate(source_column="potency", confidence=0.1)],
        ),
    ]

    result = service.confirm(table, edited, field_set)

    assert isinstance(result, service.ConfirmResult)
    assert result.proposal.is_ready is True


def test_confirm_still_blocks_when_the_chosen_column_violates_allowed_values():
    """The gate is not weakened: the same violation in the CHOSEN column --
    the one whose values actually reach the export -- must still raise."""
    table = _table()
    field_set = _unit_field_set()
    edited = [
        FieldMapping(
            target_field="compound_id", source_column="cmpd", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        FieldMapping(
            target_field="unit", source_column="potency", confidence=1.0,
            reasoning="curator says so", needs_confirmation=False,
        ),
    ]

    with pytest.raises(service.NotReadyError) as excinfo:
        service.confirm(table, edited, field_set)

    assert [m.target_field for m in excinfo.value.unclear_fields] == ["unit"]


def test_confirm_blocks_an_inferred_value_outside_allowed_values():
    """An inferred value is a chosen input: it lands in the manifest and any
    saved profile verbatim, so an ASCII 'uM' against an allowed set of
    µM/nM/% must not sail through the gate."""
    table = _table()
    field_set = _unit_field_set()
    edited = [
        FieldMapping(
            target_field="compound_id", source_column="cmpd", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        FieldMapping(
            target_field="unit", source_column=None, confidence=0.55,
            reasoning="inferred from value magnitude", needs_confirmation=False,
            inferred_value="uM",
        ),
    ]

    with pytest.raises(service.NotReadyError) as excinfo:
        service.confirm(table, edited, field_set)

    assert [m.target_field for m in excinfo.value.unclear_fields] == ["unit"]


# --- CR-02: confirm() is fail-open on omitted fields --------------------------


def test_confirm_rejects_when_edited_mappings_omit_a_field_from_the_field_set():
    """CR-02: `is_ready` is computed only over the mappings a client chose
    to send -- a client that drops a still-yellow (or any) field entirely
    must not be able to sneak a partial mapping past the gate simply by
    never sending it. `service.confirm` must assert full field coverage
    against `field_set.field_names` BEFORE reading `is_ready`, not silently
    let `canonical.assemble` emit `None` for the missing field with no
    flag."""
    table = _table()
    field_set = _field_set()  # declares compound_id + value
    edited = [
        FieldMapping(
            target_field="compound_id", source_column="cmpd", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        # "value" entirely omitted -- not sent as yellow, not sent at all.
    ]

    with pytest.raises(service.FieldCoverageError) as excinfo:
        service.confirm(table, edited, field_set)

    assert excinfo.value.missing_fields == ["value"]
    assert excinfo.value.unknown_fields == []


def test_confirm_rejects_an_unknown_field_not_declared_in_the_field_set():
    table = _table()
    field_set = _field_set()
    edited = _ready_proposal(table.headers).field_mappings + [
        FieldMapping(
            target_field="not_a_declared_field", source_column="potency",
            confidence=1.0, reasoning="curator says so", needs_confirmation=False,
        ),
    ]

    with pytest.raises(service.FieldCoverageError) as excinfo:
        service.confirm(table, edited, field_set)

    assert excinfo.value.missing_fields == []
    assert excinfo.value.unknown_fields == ["not_a_declared_field"]


# --- export(): writes only when fully clear ----------------------------------


def test_export_writes_csv_xlsx_json_and_manifest_for_a_clear_mapping(tmp_path):
    table = _table()
    field_set = _field_set()
    proposal = _ready_proposal(table.headers)
    tidy = service.canonical.assemble(table, proposal, field_set)
    export_dir = tmp_path / "out"

    manifest = service.export(
        export_dir, table, field_set, proposal, tidy, "fresh-claude", "strict"
    )

    written = {p.name for p in export_dir.iterdir()}
    assert written == {"export.csv", "export.xlsx", "export.json", "manifest.json"}
    assert manifest["provenance"] == "fresh-claude"


def test_export_raises_not_ready_error_for_a_yellow_mapping(tmp_path):
    table = _table()
    field_set = _field_set()
    blocked = MappingProposal(
        source_columns=table.headers,
        field_mappings=[
            FieldMapping(
                target_field="compound_id", source_column=None, confidence=0.4,
                reasoning="ambiguous", needs_confirmation=True,
            ),
        ],
    )
    tidy = service.canonical.assemble(table, blocked, field_set)
    export_dir = tmp_path / "out"

    with pytest.raises(service.NotReadyError):
        service.export(export_dir, table, field_set, blocked, tidy, "fresh-claude", "strict")

    assert not export_dir.exists()


# --- has_credentials(): the shared credential-presence check ----------------


def test_has_credentials_true_when_api_key_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert service.has_credentials() is True


def test_has_credentials_false_when_neither_var_set(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    assert service.has_credentials() is False


# --- AUTH-04: confirmed_by attribution seam (additive, CLI unaffected) --------


def test_confirm_threads_confirmed_by_into_the_manifest():
    """service.confirm(..., confirmed_by="a@b.com") stamps that identity into
    the returned manifest (the AUTH-04 seam the API path supplies from the
    require_verified_user-resolved user's email)."""
    table = _table()
    field_set = _field_set()
    edited = _ready_proposal(table.headers).field_mappings

    result = service.confirm(table, edited, field_set, confirmed_by="a@b.com")

    assert result.manifest["confirmed_by"] == "a@b.com"


def test_confirm_records_confirmed_by_none_on_the_cli_path():
    """The CLI path passes no confirmed_by -- the manifest records None,
    proving the seam is purely additive and the CLI is unaffected."""
    table = _table()
    field_set = _field_set()
    edited = _ready_proposal(table.headers).field_mappings

    result = service.confirm(table, edited, field_set)

    assert result.manifest["confirmed_by"] is None


def test_build_manifest_adds_the_confirmed_by_key_defaulting_to_none():
    """Regression guard for the existing manifest shape: build_manifest gains
    a keyword-only confirmed_by (default None) and always includes the key."""
    from assayingest.export.writers import build_manifest

    table = _table()
    field_set = _field_set()
    proposal = _ready_proposal(table.headers)

    manifest = build_manifest(
        field_set, table.headers, proposal, provenance="fresh-claude",
        strictness="strict", confirmed_by=None,
    )

    assert "confirmed_by" in manifest
    assert manifest["confirmed_by"] is None


# =============================================================================
# resolve_or_map judges the single-sheet path (12-05, D-12-15): row_per_record
# is the null hypothesis -- a CONFIDENT ordinary-table verdict proceeds with no
# question, and EVERY other verdict asks, answerably, with the verdict riding
# the question's proposal. judge_fn fakes at the service level (the API cannot
# reach this seam over HTTP -- tests/api/conftest.py::judging_client owns that).
# =============================================================================


from assayingest.parsing.hint import StructuralHint  # noqa: E402
from assayingest.parsing.structure.layout import (  # noqa: E402
    KeyValueBlock,
    LayoutKind,
    SheetLayout,
)


def _xlsx(tmp_path, sheets: dict[str, list[tuple]], name: str = "book.xlsx") -> str:
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name, rows in sheets.items():
        worksheet = workbook.create_sheet(sheet_name)
        for row in rows:
            worksheet.append(list(row))
    path = tmp_path / name
    workbook.save(path)
    return str(path)


#: A grid today's classifier REFUSES (blank separator + trailing prose reads as
#: multiple_tables) -- so a MapResult out of it proves the VERDICT steered the
#: read, not the heuristic (the 12-03 non-vacuous-RED discipline).
_REFUSED_BY_CLASSIFIER = [
    ("cmpd", "potency"),
    ("A-1", "1.5"),
    ("A-2", "2.5"),
    (None, None),
    ("Assay run under Westgard multirules; QC review passed.", None),
]

_CLEAN_GRID = [
    ("cmpd", "potency"),
    ("A-1", "1.5"),
    ("A-2", "2.5"),
]


def _generic_mapper(table, field_set, client=None, **kwargs):
    return MappingProposal(
        source_columns=list(table.headers),
        field_mappings=[
            FieldMapping(
                target_field=name, source_column=None, confidence=1.0,
                reasoning="stub", needs_confirmation=False,
            )
            for name in field_set.field_names
        ],
    )


def _recording_judge(verdicts: dict[str, SheetLayout]):
    """A judge_fn fake that records every call -- the seam-level sibling of the
    tests/test_describe_workbook.py explode idiom. Recording (not just raising)
    matters: the availability boundary swallows a raising judge, so an explode
    alone could pass vacuously. `calls == []` is the real zero-calls proof."""
    calls: list[dict] = []

    def _fn(grids, *, headers_only):
        calls.append({"sheets": list(grids), "headers_only": headers_only})
        return {name: verdicts[name] for name in grids if name in verdicts}

    return _fn, calls


def _rpr(confidence: float = 1.0, header_row_index: int | None = 0, **kwargs) -> SheetLayout:
    return SheetLayout(
        kind=LayoutKind.ROW_PER_RECORD, confidence=confidence,
        reasoning="an ordinary table", header_row_index=header_row_index, **kwargs,
    )


def test_a_confident_row_per_record_verdict_proceeds_with_no_question(
    tmp_path, monkeypatch
):
    """The null hypothesis (D-12-15): a confident row_per_record verdict is
    exactly today's behaviour -- no question, no human in the loop -- and its
    row range steers the read (the trailing prose the classifier chokes on is
    trimmed away per the verdict)."""
    monkeypatch.setattr(service, "propose_mapping", _generic_mapper)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    path = _xlsx(tmp_path, {"Data": _REFUSED_BY_CLASSIFIER})
    judge, calls = _recording_judge(
        {"Data": _rpr(confidence=0.95, header_row_index=0, first_data_row=1, last_data_row=2)}
    )

    result = service.resolve_or_map(path, _field_set(), store=None, judge_fn=judge)

    assert isinstance(result, service.MapResult)
    assert result.table.headers == ["cmpd", "potency"]
    assert len(result.table.rows) == 2  # the Westgard prose is provably absent
    assert len(calls) == 1  # judged exactly once


def test_a_confident_verdict_naming_no_header_row_reads_the_ordinary_way(
    tmp_path, monkeypatch
):
    """The null-hypothesis corner: a confident row_per_record that names NO
    header row cannot steer parse (the T-12-08 guard would fail it closed to a
    question) -- so 'read it the ordinary way' means exactly that: today's
    header detection runs, silently, and the upload still maps."""
    monkeypatch.setattr(service, "propose_mapping", _generic_mapper)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    path = _xlsx(tmp_path, {"Data": _CLEAN_GRID})
    judge, _calls = _recording_judge({"Data": _rpr(confidence=1.0, header_row_index=None)})

    result = service.resolve_or_map(path, _field_set(), store=None, judge_fn=judge)

    assert isinstance(result, service.MapResult)
    assert result.table.headers == ["cmpd", "potency"]


_ASKING_VERDICTS = [
    SheetLayout(
        kind=LayoutKind.KEY_VALUE, confidence=0.97, reasoning="labels down the side",
        key_value_blocks=(KeyValueBlock(0, (1,), 0, 2),),
    ),
    SheetLayout(kind=LayoutKind.WIDE_MATRIX, confidence=0.97, reasoning="a matrix layout"),
    SheetLayout(kind=LayoutKind.MULTIPLE_TABLES, confidence=0.97, reasoning="two stacked tables"),
    SheetLayout(kind=LayoutKind.NOT_A_TABLE, confidence=0.97, reasoning="a banner sheet"),
    SheetLayout(kind=LayoutKind.UNKNOWN, confidence=0.0, reasoning="the judge could not tell"),
]


@pytest.mark.parametrize(
    "verdict", _ASKING_VERDICTS, ids=[v.kind.value for v in _ASKING_VERDICTS]
)
def test_every_other_verdict_returns_the_answerable_layout_question(
    tmp_path, monkeypatch, verdict
):
    """EVERY verdict but a confident row_per_record changes what a value IS,
    and must be confirmed by a human (D-12-15) -- even a CONFIDENT key_value:
    an unconfirmed un-pivot would be a silent reshaping of the data. The
    question carries the verdict in its proposal (blocks included) and its
    reasoning, so the human is told WHY they are being asked."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    path = _xlsx(tmp_path, {"Data": _CLEAN_GRID})
    judge, _calls = _recording_judge({"Data": verdict})

    result = service.resolve_or_map(path, _field_set(), store=None, judge_fn=judge)

    assert isinstance(result, StructureQuestion)
    assert result.answerable_by_hint is True
    assert result.proposal is not None
    assert result.proposal.layout == verdict  # blocks and indices survive intact
    assert verdict.reasoning in result.reason
    assert result.evidence_rows


def test_a_low_confidence_row_per_record_verdict_asks_before_reading(
    tmp_path, monkeypatch
):
    """A low-confidence row_per_record is NOT the null hypothesis -- it asks,
    with the verdict's header row riding the proposal so the panel can
    pre-fill the answer (the off-by-one fix path, 12-UI-SPEC)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    path = _xlsx(tmp_path, {"Data": _CLEAN_GRID})
    judge, _calls = _recording_judge({"Data": _rpr(confidence=0.4, header_row_index=0)})

    result = service.resolve_or_map(path, _field_set(), store=None, judge_fn=judge)

    assert isinstance(result, StructureQuestion)
    assert result.answerable_by_hint is True
    assert result.proposal.layout.header_row_index == 0


def test_a_verdict_riding_the_hint_costs_zero_judge_calls(tmp_path, monkeypatch):
    """The zero-extra-calls proof (D-12-02/D-12-14): a verdict arriving on the
    hint -- the retained-manifest path -- is never re-judged. The judge_fn
    records (and would raise); `calls == []` is the proof."""
    monkeypatch.setattr(service, "propose_mapping", _generic_mapper)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    path = _xlsx(tmp_path, {"Data": _CLEAN_GRID})

    def _exploding_judge(grids, *, headers_only):
        raise AssertionError("the judge must NOT be called: the verdict rides the hint")

    calls: list = []

    def _recording_exploding_judge(grids, *, headers_only):
        calls.append(list(grids))
        return _exploding_judge(grids, headers_only=headers_only)

    result = service.resolve_or_map(
        path, _field_set(), store=None,
        hint=StructuralHint(layout=_rpr(confidence=1.0, header_row_index=0)),
        judge_fn=_recording_exploding_judge, layout_confirmed=False,
    )

    assert isinstance(result, service.MapResult)
    assert calls == []


def test_a_confirmed_layout_on_the_hint_is_read_not_re_asked(tmp_path, monkeypatch):
    """Round trip A's service half: a layout the HUMAN confirmed (the
    structural-hint resolve route's posture, layout_confirmed's default) flows
    into parse as the confirmation it is -- the key-value sheet is un-pivoted,
    never bounced back to the same question (the loop is closed)."""
    monkeypatch.setattr(service, "propose_mapping", _generic_mapper)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    path = _xlsx(
        tmp_path,
        {"Data": [("Name", "Ada"), ("Score", "1.5"), ("City", "Rome")]},
    )
    confirmed = SheetLayout(
        kind=LayoutKind.KEY_VALUE, confidence=1.0, reasoning="confirmed by curator",
        key_value_blocks=(KeyValueBlock(0, (1,), 0, 2),),
    )
    judge, calls = _recording_judge({})

    result = service.resolve_or_map(
        path, _field_set(), store=None,
        hint=StructuralHint(layout=confirmed), judge_fn=judge,
    )

    assert isinstance(result, service.MapResult)
    assert result.table.headers == ["Name", "Score", "City"]
    assert result.table.rows == [["Ada", "1.5", "Rome"]]
    assert calls == []


def test_a_raising_judge_reads_the_ordinary_way_this_wave(tmp_path, monkeypatch, caplog):
    """Judge unavailable OR failing == no verdict == today's parse, THIS wave
    (the fail-closed switch is Wave C, plan 12-07). Logged once, naming the
    consequence -- never logged AND raised."""
    import logging

    monkeypatch.setattr(service, "propose_mapping", _generic_mapper)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    path = _xlsx(tmp_path, {"Data": _CLEAN_GRID})

    def _raising_judge(grids, *, headers_only):
        raise RuntimeError("simulated outage")

    with caplog.at_level(logging.WARNING, logger="assayingest.service"):
        result = service.resolve_or_map(
            path, _field_set(), store=None, judge_fn=_raising_judge
        )

    assert isinstance(result, service.MapResult)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "ordinary" in warnings[0].getMessage()


def test_a_csv_never_reaches_the_judge(monkeypatch):
    """D-12-18, said out loud: the judge is an .xlsx concern. A CSV upload
    never pays a judge call and parses exactly as today."""
    monkeypatch.setattr(service, "propose_mapping", _generic_mapper)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    judge, calls = _recording_judge({})

    result = service.resolve_or_map(str(NOVASCREEN_01), _field_set(), store=None, judge_fn=judge)

    assert isinstance(result, service.MapResult)
    assert calls == []


def test_the_callers_headers_only_reaches_the_single_sheet_judge(tmp_path, monkeypatch):
    """The fourth headers_only enforcement site is per-call-site (D-12-06):
    the caller's privacy toggle must arrive at the judge on THIS path too."""
    monkeypatch.setattr(service, "propose_mapping", _generic_mapper)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    path = _xlsx(tmp_path, {"Data": _CLEAN_GRID})
    judge, calls = _recording_judge({"Data": _rpr()})

    result = service.resolve_or_map(
        path, _field_set(), store=None, judge_fn=judge, headers_only=True
    )

    assert isinstance(result, service.MapResult)
    assert calls == [{"sheets": ["Data"], "headers_only": True}]


def test_a_multi_sheet_workbook_without_an_explicit_sheet_is_not_judged_here(
    tmp_path, monkeypatch
):
    """The sheet question owns the multi-sheet case (D-12-15 rejected forcing
    it here) -- with no explicit sheet there is no honest target to judge, so
    resolve_or_map never guesses one: parse ranks (and here hesitates over two
    equally data-like sheets) exactly as today, and the judge is never paid."""
    monkeypatch.setattr(service, "propose_mapping", _generic_mapper)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    path = _xlsx(
        tmp_path,
        {
            "Week 1": [("Compound Name", "IC50")] + [(f"CPD-{i}", 10.5 + i) for i in range(12)],
            "Week 2": [("Sample", "Result")] + [(f"S-{i}", 40 + i) for i in range(3)],
        },
    )
    judge, calls = _recording_judge({})

    result = service.resolve_or_map(path, _field_set(), store=None, judge_fn=judge)

    assert calls == []  # never judged: there is no honest single target
    # Today's D-09 ranking gate, byte for byte: two data-like sheets hesitate.
    assert isinstance(result, StructureQuestion)
    assert "which sheet" in result.unsure_about


def test_an_explicit_sheet_is_judged_by_name(tmp_path, monkeypatch):
    """An explicit `sheet=` names the target, so the judge sees exactly that
    sheet's grid -- one call, one sheet, never the whole workbook here."""
    monkeypatch.setattr(service, "propose_mapping", _generic_mapper)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    path = _xlsx(
        tmp_path,
        {
            "Week 1": [("Compound Name", "IC50")] + [(f"CPD-{i}", 10.5 + i) for i in range(12)],
            "Week 2": [("Sample", "Result")] + [(f"S-{i}", 40 + i) for i in range(3)],
        },
    )
    judge, calls = _recording_judge({"Week 2": _rpr(confidence=1.0, header_row_index=0)})

    result = service.resolve_or_map(path, _field_set(), store=None, sheet="Week 2", judge_fn=judge)

    assert isinstance(result, service.MapResult)
    assert result.table.headers == ["Sample", "Result"]
    assert calls == [{"sheets": ["Week 2"], "headers_only": False}]
