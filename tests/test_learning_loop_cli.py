"""The learning-loop money shot, end to end through the CLI, offline
(LEARN-03/04, D-05/06/08, Pitfall 2/3). Written test-first (TDD RED)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from assayingest import cli
from assayingest.cli import run
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.loader import load as load_field_set
from assayingest.learning.profile import LearnedProfile, StoredFieldMapping
from assayingest.learning.reconstruct import (
    _resolve_new_header,
    reconstruct_proposal,
    stored_mapping_from,
)
from assayingest.learning.signature import column_signature
from assayingest.parsing.table import parse_file

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"
PRESET = Path(__file__).resolve().parent.parent / "presets" / "assay-potency.yaml"


def _ready_field_mappings() -> list[FieldMapping]:
    """A fully-clear mapping for novascreen_batch01/02 (byte-identical
    headers): cmpd, assay, potency, "", target_gene, replicates, date."""
    return [
        FieldMapping(
            target_field="compound_id",
            source_column="cmpd",
            confidence=1.0,
            reasoning="exact match",
            needs_confirmation=False,
        ),
        FieldMapping(
            target_field="assay_type",
            source_column="assay",
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
        FieldMapping(
            target_field="unit",
            source_column=None,
            confidence=1.0,
            reasoning="confirmed by curator",
            needs_confirmation=False,
            inferred_value="nM",
        ),
        FieldMapping(
            target_field="target",
            source_column="target_gene",
            confidence=1.0,
            reasoning="exact match",
            needs_confirmation=False,
        ),
        FieldMapping(
            target_field="n_replicates",
            source_column="replicates",
            confidence=1.0,
            reasoning="exact match",
            needs_confirmation=False,
        ),
        FieldMapping(
            target_field="assay_date",
            source_column="date",
            confidence=1.0,
            reasoning="exact match",
            needs_confirmation=False,
        ),
    ]


def _blocked_field_mappings(field_names: list[str]) -> list[FieldMapping]:
    return [
        FieldMapping(
            target_field=name,
            source_column=None,
            confidence=0.4,
            reasoning="ambiguous",
            needs_confirmation=True,
        )
        for name in field_names
    ]


# --- reconstruction hazard (P1, Pitfall 2) ----------------------------------


def test_reconstruction_resolves_case_and_whitespace_varied_headers():
    saved_headers = ["Compound ID", "Assay"]
    mapping = [
        FieldMapping(
            target_field="compound_id",
            source_column="Compound ID",
            confidence=1.0,
            reasoning="exact match",
            needs_confirmation=False,
        ),
        FieldMapping(
            target_field="assay_type",
            source_column="Assay",
            confidence=1.0,
            reasoning="exact match",
            needs_confirmation=False,
        ),
    ]
    profile = LearnedProfile(
        profile_id="hazard-1",
        field_set_signature="fs-sig",
        column_signature=column_signature(saved_headers),
        field_mappings=tuple(stored_mapping_from(m, saved_headers) for m in mapping),
        structural_hint=None,
        created_at=datetime.now(UTC).isoformat(),
    )

    # A deliberately case/whitespace-VARIED second fixture -- reusing
    # `saved_headers` verbatim would not exercise the hazard (Pitfall 2):
    # the signature still matches, but no header is byte-identical.
    new_headers = ["  compound   id ", "assay"]
    assert column_signature(new_headers) == profile.column_signature

    proposal = reconstruct_proposal(profile, new_headers)

    resolved = {m.target_field: m.source_column for m in proposal.field_mappings}
    assert resolved["compound_id"] == "  compound   id "
    assert resolved["assay_type"] == "assay"
    assert all(not m.needs_confirmation for m in proposal.field_mappings)
    assert all(m.confidence == 1.0 for m in proposal.field_mappings)


# --- duplicate/blank occurrence disambiguation ------------------------------


def test_resolve_new_header_disambiguates_by_left_to_right_occurrence():
    # Three headers that all normalise to "dup" but keep a different literal
    # casing per occurrence -- lets the test OBSERVE which occurrence was
    # actually picked (a genuine duplicate-blank pair returns "" either way
    # and can't prove which position was chosen by string comparison alone).
    headers = ["A", "DUP", "b", "dup", "C", "Dup"]

    assert _resolve_new_header(headers, "dup", 0) == "DUP"
    assert _resolve_new_header(headers, "dup", 1) == "dup"
    assert _resolve_new_header(headers, "dup", 2) == "Dup"


def test_reconstruct_proposal_resolves_two_blank_columns_to_distinct_positions():
    profile = LearnedProfile(
        profile_id="dup-1",
        field_set_signature="fs-sig",
        column_signature="col-sig",
        field_mappings=(
            StoredFieldMapping(
                target_field="field_a",
                source_column_normalised="",
                source_column_occurrence=0,
            ),
            StoredFieldMapping(
                target_field="field_b",
                source_column_normalised="",
                source_column_occurrence=1,
            ),
        ),
        structural_hint=None,
        created_at=datetime.now(UTC).isoformat(),
    )
    new_headers = ["A", "", "B", ""]

    proposal = reconstruct_proposal(profile, new_headers)

    resolved = {m.target_field: m.source_column for m in proposal.field_mappings}
    assert resolved["field_a"] == ""
    assert resolved["field_b"] == ""
    # Both blanks resolve (neither silently drops its column) -- the
    # occurrence-rank scan proven directly at the unit level above.
    assert all(m.source_column is not None for m in proposal.field_mappings)


def test_reconstruct_proposal_uses_occurrence_to_pick_the_right_duplicate():
    profile = LearnedProfile(
        profile_id="dup-2",
        field_set_signature="fs-sig",
        column_signature="col-sig",
        field_mappings=(
            StoredFieldMapping(
                target_field="first", source_column_normalised="dup", source_column_occurrence=0
            ),
            StoredFieldMapping(
                target_field="second", source_column_normalised="dup", source_column_occurrence=1
            ),
        ),
        structural_hint=None,
        created_at=datetime.now(UTC).isoformat(),
    )
    new_headers = ["DUP", "dup"]

    proposal = reconstruct_proposal(profile, new_headers)

    resolved = {m.target_field: m.source_column for m in proposal.field_mappings}
    assert resolved["first"] == "DUP"
    assert resolved["second"] == "dup"


# --- WR-01: fail closed when duplicate/blank headers are indistinguishable --


def test_reconstruct_proposal_fails_closed_when_blank_columns_are_swapped():
    """A stored mapping resolved by (normalised="", occurrence rank) alone is
    order-dependent, but `column_signature` is order-independent -- a later
    same-signature file can carry its blank columns in a different physical
    order and silently misroute data at confidence 1.0 (P1). The affected
    fields must instead fail closed to needs_confirmation=True."""
    profile = LearnedProfile(
        profile_id="dup-swap",
        field_set_signature="fs-sig",
        column_signature=column_signature(["", ""]),
        field_mappings=(
            StoredFieldMapping(
                target_field="value", source_column_normalised="", source_column_occurrence=0
            ),
            StoredFieldMapping(
                target_field="unit", source_column_normalised="", source_column_occurrence=1
            ),
        ),
        structural_hint=None,
        created_at=datetime.now(UTC).isoformat(),
    )
    swapped_headers = ["", ""]  # same signature; occurrence rank can't disambiguate
    assert column_signature(swapped_headers) == profile.column_signature

    proposal = reconstruct_proposal(profile, swapped_headers)

    resolved = {m.target_field: m for m in proposal.field_mappings}
    assert resolved["value"].needs_confirmation is True
    assert resolved["unit"].needs_confirmation is True


def test_reconstruct_proposal_does_not_flag_distinct_reordered_headers():
    """Distinct headers reordered stay auto-applied at 1.0 -- only genuinely
    indistinguishable (duplicate/blank) headers must fail closed."""
    profile = LearnedProfile(
        profile_id="distinct-reorder",
        field_set_signature="fs-sig",
        column_signature=column_signature(["Compound", "Value"]),
        field_mappings=(
            StoredFieldMapping(
                target_field="compound_id",
                source_column_normalised="compound",
                source_column_occurrence=0,
            ),
            StoredFieldMapping(
                target_field="value",
                source_column_normalised="value",
                source_column_occurrence=0,
            ),
        ),
        structural_hint=None,
        created_at=datetime.now(UTC).isoformat(),
    )
    reordered_headers = ["Value", "Compound"]

    proposal = reconstruct_proposal(profile, reordered_headers)

    resolved = {m.target_field: m for m in proposal.field_mappings}
    assert resolved["compound_id"].needs_confirmation is False
    assert resolved["compound_id"].confidence == 1.0
    assert resolved["value"].needs_confirmation is False


# --- money shot: offline, no credentials, no Claude call --------------------


def test_money_shot_auto_applies_offline_zero_yellow_no_claude_call(tmp_path, monkeypatch, capsys, profile_store):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("propose_mapping must never be called on a profile hit")

    monkeypatch.setattr(cli, "propose_mapping", _fail_if_called)

    field_set = load_field_set(PRESET)
    table1 = parse_file(DATA / "novascreen_batch01.csv")
    db_path = tmp_path / "profiles.db"
    store = profile_store

    # Seed the profile directly -- simulates a curator who already
    # confirmed batch01's mapping once and saved it.
    stored_mappings = tuple(
        stored_mapping_from(m, table1.headers) for m in _ready_field_mappings()
    )
    profile = LearnedProfile(
        profile_id="money-shot-1",
        field_set_signature=field_set.signature,
        column_signature=column_signature(table1.headers),
        field_mappings=stored_mappings,
        structural_hint=None,
        created_at=datetime.now(UTC).isoformat(),
    )
    store.save(profile)

    exit_code = run(
        str(DATA / "novascreen_batch02.csv"),
        field_set=field_set,
        store=profile_store,
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert f"applied saved profile {profile.profile_id}" in out
    assert "no Claude call" in out

    data, _ = json.JSONDecoder().raw_decode(out, out.index("{"))
    assert data["ready"] is True
    assert all(not m["needs_confirmation"] for m in data["field_mappings"])
    assert all(m["confidence"] == 1.0 for m in data["field_mappings"])


# --- save gate (D-06) --------------------------------------------------------


def test_save_profile_flag_refuses_to_save_a_blocked_mapping(tmp_path, monkeypatch, profile_store):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    field_set = load_field_set(PRESET)

    def _blocked(table, field_set, client=None, **kwargs):
        return MappingProposal(
            source_columns=table.headers,
            field_mappings=_blocked_field_mappings(field_set.field_names),
        )

    monkeypatch.setattr(cli, "propose_mapping", _blocked)

    db_path = tmp_path / "profiles.db"
    exit_code = run(
        str(DATA / "novascreen_batch01.csv"),
        field_set=field_set,
        store=profile_store,
        save_profile=True,
    )

    assert exit_code == 5
    table = parse_file(DATA / "novascreen_batch01.csv")
    store = profile_store
    assert store.find(field_set.signature, column_signature(table.headers)) is None


def test_save_profile_flag_saves_a_fully_clear_mapping(tmp_path, monkeypatch, profile_store):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    field_set = load_field_set(PRESET)
    table = parse_file(DATA / "novascreen_batch01.csv")

    def _ready(t, fs, client=None, **kwargs):
        return MappingProposal(source_columns=t.headers, field_mappings=_ready_field_mappings())

    monkeypatch.setattr(cli, "propose_mapping", _ready)

    db_path = tmp_path / "profiles.db"
    exit_code = run(
        str(DATA / "novascreen_batch01.csv"),
        field_set=field_set,
        store=profile_store,
        save_profile=True,
    )

    assert exit_code == 0
    store = profile_store
    found = store.find(field_set.signature, column_signature(table.headers))
    assert found is not None
    assert {m.target_field for m in found.field_mappings} == set(field_set.field_names)


# --- fallback (LEARN-04) + credential-check relocation (Pitfall 3) ----------


def test_no_seeded_profile_falls_back_to_claude_and_still_requires_credentials(tmp_path, monkeypatch, capsys, profile_store):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("must not be called: credentials are missing")

    monkeypatch.setattr(cli, "propose_mapping", _fail_if_called)

    field_set = load_field_set(PRESET)
    db_path = tmp_path / "profiles.db"
    exit_code = run(
        str(DATA / "novascreen_batch01.csv"),
        field_set=field_set,
        store=profile_store,
    )

    assert exit_code == 3
    assert "credentials" in capsys.readouterr().err


def test_a_seeded_profile_for_a_different_signature_never_auto_applies(tmp_path, monkeypatch, capsys, profile_store):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("must not be called: credentials are missing")

    monkeypatch.setattr(cli, "propose_mapping", _fail_if_called)

    field_set = load_field_set(PRESET)
    db_path = tmp_path / "profiles.db"
    store = profile_store
    store.save(
        LearnedProfile(
            profile_id="other-signature",
            field_set_signature=field_set.signature,
            column_signature="totally-different-signature",
            field_mappings=(),
            structural_hint=None,
            created_at=datetime.now(UTC).isoformat(),
        )
    )

    exit_code = run(
        str(DATA / "novascreen_batch01.csv"),
        field_set=field_set,
        store=profile_store,
    )

    assert exit_code == 3
    assert "credentials" in capsys.readouterr().err


# --- .gitignore covers WAL/-shm/-journal side files (Pitfall 4) ------------


def test_assayingest_dir_is_gitignored():
    gitignore = (Path(__file__).resolve().parent.parent / ".gitignore").read_text()
    assert "/.assayingest/" in gitignore
