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
from assayingest.domain.models import FieldMapping, MappingProposal
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
