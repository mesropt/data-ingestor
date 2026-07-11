"""POST /api/upload -- the FastAPI transport layer's walking-skeleton slice
(API-01/03, UI-02), TDD RED-first (04-02).

Reuses the exact monkeypatch/fixture idioms `tests/test_cli_run.py` and
`tests/test_learning_loop_cli.py` already established for the CLI's own
version of this same seam (04-RESEARCH.md "Testing the API"): monkeypatch
`assayingest.service.propose_mapping` (never a route-level reimplementation
of the mapper), the same `novascreen_batch01.csv`/`novascreen_batch02.csv`
same-signature fixture pair, and the same `_ready_field_mappings()` builder
shape.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from assayingest import service
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.loader import load as load_field_set
from assayingest.fields.models import Field, FieldSet
from assayingest.learning.profile import LearnedProfile
from assayingest.learning.reconstruct import stored_mapping_from
from assayingest.learning.signature import column_signature
from assayingest.learning.sqlite_store import SqliteProfileStore
from assayingest.parsing.hint import StructuralHint, StructureQuestion
from assayingest.parsing.table import RawTable, parse_file
from assayingest.validation.validator import validate

DATA = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic"
PRESET = Path(__file__).resolve().parent.parent.parent / "presets" / "assay-potency.yaml"
NOVASCREEN_01 = DATA / "novascreen_batch01.csv"
NOVASCREEN_02 = DATA / "novascreen_batch02.csv"


def _ready_field_mappings() -> list[FieldMapping]:
    """A fully-clear mapping for novascreen_batch01/02 (byte-identical
    headers: cmpd, assay, potency, "", target_gene, replicates, date) --
    mirrors `tests/test_learning_loop_cli.py::_ready_field_mappings`
    exactly, duplicated locally per this project's per-test-file helper
    convention (test_service.py does the same)."""
    return [
        FieldMapping(
            target_field="compound_id", source_column="cmpd", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        FieldMapping(
            target_field="assay_type", source_column="assay", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        FieldMapping(
            target_field="value", source_column="potency", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        FieldMapping(
            target_field="unit", source_column=None, confidence=1.0,
            reasoning="confirmed by curator", needs_confirmation=False,
            inferred_value="nM",
        ),
        FieldMapping(
            target_field="target", source_column="target_gene", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        FieldMapping(
            target_field="n_replicates", source_column="replicates", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        FieldMapping(
            target_field="assay_date", source_column="date", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
    ]


# --- Task 1: app wiring + DI seams + wire models -----------------------------


def test_upload_happy_path_returns_mapping_kind_with_upload_token(monkeypatch, tmp_path):
    from assayingest.api.app import app
    from assayingest.api.deps import get_profile_store

    monkeypatch.setattr(
        service, "propose_mapping",
        lambda table, fs, client=None, **kw: MappingProposal(
            source_columns=table.headers, field_mappings=_ready_field_mappings()
        ),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    field_set = load_field_set(PRESET)
    store = SqliteProfileStore(tmp_path / "profiles.db")
    app.dependency_overrides[get_profile_store] = lambda: store
    client = TestClient(app)

    with open(NOVASCREEN_01, "rb") as f:
        response = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", f, "text/csv")},
            data={"field_set": json.dumps(field_set.to_dict())},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "mapping"
    assert body["source_columns"]
    assert body["field_mappings"]
    assert body["provenance"] == "fresh-claude"
    assert body["upload_token"]
    assert "validator_note" in body["field_mappings"][0]


def test_mapping_response_from_proposal_includes_validator_note():
    """wire.MappingResponse's shape: field_mappings carry
    target_field/source_column/confidence/reasoning/needs_confirmation/
    inferred_value/alternatives[]/validator_note -- `validator_note` is the
    one field `cli.proposal_to_dict`'s dict omits (PATTERNS.md), so the wire
    model must add it, not merely mirror the dict byte-for-byte."""
    from assayingest.api.wire import MappingResponse

    table = RawTable(
        headers=["cmpd", "potency"], rows=[["NVS-1", "12.5"]], source_name="x.csv"
    )
    field_set = FieldSet(fields=(Field(name="compound_id"), Field(name="value")))
    proposal = MappingProposal(
        source_columns=table.headers,
        field_mappings=[
            FieldMapping(
                target_field="compound_id", source_column="cmpd", confidence=1.0,
                reasoning="exact match", needs_confirmation=False,
            ),
        ],
    )
    proposal = validate(table, proposal, field_set)

    response = MappingResponse.from_proposal(proposal, "fresh-claude", "token-123")

    assert response.kind == "mapping"
    assert response.upload_token == "token-123"
    field = response.field_mappings[0]
    assert field.target_field == "compound_id"
    assert field.validator_note is not None
    assert field.alternatives == []


def test_dependency_seams_are_overridable_and_auto_apply_reaches_a_tmp_path_store(
    tmp_path,
):
    """get_profile_store/get_field_set_store/get_anthropic_client are
    overridable via app.dependency_overrides -- proven by injecting a
    tmp-path SqliteProfileStore that already holds a matching profile: the
    auto-apply branch reaches it with zero Anthropic client construction and
    zero credentials configured (mirrors service.py's own
    no-client/no-credentials-on-hit invariant, RESEARCH.md Pitfall 3)."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_profile_store

    field_set = load_field_set(PRESET)
    table = parse_file(NOVASCREEN_01)
    store = SqliteProfileStore(tmp_path / "profiles.db")
    profile = LearnedProfile(
        profile_id="di-seam-1",
        field_set_signature=field_set.signature,
        column_signature=column_signature(table.headers),
        field_mappings=tuple(
            stored_mapping_from(m, table.headers) for m in _ready_field_mappings()
        ),
        structural_hint=None,
        created_at="2026-01-01T00:00:00+00:00",
    )
    store.save(profile)

    app.dependency_overrides[get_profile_store] = lambda: store
    client = TestClient(app)
    with open(NOVASCREEN_01, "rb") as f:
        response = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", f, "text/csv")},
            data={"field_set": json.dumps(field_set.to_dict())},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["provenance"] == "auto-applied-from-profile"
    assert body["ready"] is True
