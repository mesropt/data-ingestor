"""Reconcile-on-upload TRANSPORT layer (08-02, TDD RED-first).

Wires the 08-01 reconcile service core into FastAPI as pure adapter code:
`/api/upload` grows an optional map-file + target-Schema + vendor branch that
returns the discriminated `kind="reconcile_question"` on a map-file-vs-master
conflict (augmenting/mapping NOTHING until the human resolves), and a new
`POST /api/reconcile/resolve` applies the human's per-conflict choice and
returns the terminal `kind="mapping"` MappingResponse into the existing
yellow-flag review under the unchanged `/api/confirm` gate.

Mirrors `tests/api/test_upload.py` / `tests/api/test_confirm_aliases_route.py`
idioms exactly: monkeypatch `service.propose_mapping` (never a route-level
reimplementation of the mapper), override `get_profile_store`/`get_schema_store`/
`get_current_user` with tmp-path stores + an injected `User`, seed a promoted
Schema via `service.promote`, and drive a real synthetic CSV + a JSON master-map
map file through `TestClient`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from assayingest import service
from assayingest.domain.models import (
    Alias,
    FieldMapping,
    MappingProposal,
    ReconcileConflict,
    ReconcileQuestion,
)
from assayingest.fields.loader import load as load_field_set
from assayingest.fields.models import Field, FieldSet

from .conftest import unverified_user as _unverified_user
from .conftest import verified_user as _verified_user

DATA = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic"
PRESET = Path(__file__).resolve().parent.parent.parent / "presets" / "assay-potency.yaml"
NOVASCREEN_01 = DATA / "novascreen_batch01.csv"

_TS = "2026-01-01T00:00:00+00:00"
_SCHEMA_NAME = "assay-potency"


# --- builders (mirror tests/test_reconcile_service.py) -----------------------


def _alias(vendor: str, source_column: str) -> Alias:
    return Alias(
        vendor=vendor,
        source_column=source_column,
        provenance_kind="from_map_file",
        provenance_actor="map-file-source",
        created_at=_TS,
    )


def _envelope(field_aliases: dict[str, list[Alias]], *, name: str = _SCHEMA_NAME) -> dict:
    """A Phase-07 master-map JSON envelope -- the uploaded map file format."""
    return {
        "schema_version": 1,
        "id": "e1",
        "name": name,
        "created_by": None,
        "created_at": _TS,
        "fields": [
            {"name": fname, "aliases": [a.to_dict() for a in aliases]}
            for fname, aliases in field_aliases.items()
        ],
    }


# --- Task 1: reconcile wire models + UploadEntry retention fields ------------


def test_reconcile_question_response_wire_shape_from_question():
    """ReconcileQuestionResponse.from_question spreads ReconcileQuestion.to_dict()
    verbatim (mirroring StructuralQuestionResponse.from_question) -- kind, token,
    schema_name, vendor, and a conflicts list of the four-key dicts."""
    from assayingest.api.wire import ReconcileQuestionResponse

    question = ReconcileQuestion(
        (
            ReconcileConflict(
                vendor="acme", source_column="cmpd",
                master_field="value", map_file_field="compound_id",
            ),
        )
    )

    resp = ReconcileQuestionResponse.from_question(question, "tok-1", _SCHEMA_NAME, "acme")

    assert resp.kind == "reconcile_question"
    assert resp.upload_token == "tok-1"
    assert resp.schema_name == _SCHEMA_NAME
    assert resp.vendor == "acme"
    assert resp.conflicts == [
        {
            "vendor": "acme",
            "source_column": "cmpd",
            "master_field": "value",
            "map_file_field": "compound_id",
        }
    ]


def test_reconcile_resolve_request_parses_valid_choice():
    """ReconcileResolveRequest parses {upload_token, choices:[{vendor,
    source_column, decision}]} with the decision Literal accepted."""
    from assayingest.api.wire import ReconcileResolveRequest

    req = ReconcileResolveRequest(
        upload_token="tok",
        choices=[
            {"vendor": "acme", "source_column": "cmpd", "decision": "take_map_file"},
            {"vendor": "acme", "source_column": "assay", "decision": "keep_master"},
        ],
    )

    assert req.upload_token == "tok"
    assert req.choices[0].vendor == "acme"
    assert req.choices[0].source_column == "cmpd"
    assert req.choices[0].decision == "take_map_file"
    assert req.choices[1].decision == "keep_master"


def test_reconcile_resolve_request_rejects_unknown_decision():
    """An invalid decision value is a Pydantic ValidationError at the boundary
    (422), never a silent mis-apply -- the decision is a Literal, not a bare str."""
    from assayingest.api.wire import ReconcileResolveRequest

    with pytest.raises(ValidationError):
        ReconcileResolveRequest(
            upload_token="tok",
            choices=[{"vendor": "acme", "source_column": "cmpd", "decision": "bogus"}],
        )


def test_reconcile_choice_in_is_the_choice_element_type():
    """ReconcileChoiceIn is the element type of ReconcileResolveRequest.choices."""
    from assayingest.api.wire import ReconcileChoiceIn

    choice = ReconcileChoiceIn(vendor="acme", source_column="cmpd", decision="keep_master")
    assert choice.decision == "keep_master"
    with pytest.raises(ValidationError):
        ReconcileChoiceIn(vendor="acme", source_column="cmpd", decision="nope")


def test_upload_entry_carries_additive_retention_fields():
    """UploadEntry accepts map_envelope/target_schema_name/vendor, defaulting to
    None -- retained ONLY while a reconcile question is pending."""
    from assayingest.api.state import UploadEntry

    entry = UploadEntry(
        field_set=None, headers_only=False, tmp_path="/tmp/x.csv",
        map_envelope={"name": "assay"}, target_schema_name=_SCHEMA_NAME, vendor="acme",
    )
    assert entry.map_envelope == {"name": "assay"}
    assert entry.target_schema_name == _SCHEMA_NAME
    assert entry.vendor == "acme"


def test_upload_entry_without_retention_fields_still_constructs(schema_store):
    """The new fields are purely additive -- an existing UploadEntry(...) call
    (no reconcile fields) still constructs, all three defaulting to None."""
    from assayingest.api.state import UploadEntry

    entry = UploadEntry(field_set=None, headers_only=False, tmp_path=None)
    assert entry.map_envelope is None
    assert entry.target_schema_name is None
    assert entry.vendor is None


# --- Task 2/3 shared TestClient scaffolding ----------------------------------


def _promoted_store(store, *, master_aliases=None, fields=("compound_id", "value")):
    """A `PostgresSchemaStore` promoted to a governed Schema named
    `_SCHEMA_NAME`, optionally pre-seeded with `master_aliases`
    (`{field_name: [Alias, ...]}` as MANUAL curator aliases)."""
    field_set = FieldSet(name=_SCHEMA_NAME, fields=tuple(Field(name=n) for n in fields))
    service.promote(field_set, created_by="curator@example.com", store=store)
    schema = store.get_schema(_SCHEMA_NAME)
    for field_name, aliases in (master_aliases or {}).items():
        for a in aliases:
            store.add_alias(
                schema.id, field_name,
                Alias(vendor=a.vendor, source_column=a.source_column,
                      provenance_kind="manual", provenance_actor="curator@example.com",
                      created_at=_TS),
            )
    return store, store.get_schema(_SCHEMA_NAME).id


def _reconcile_field_set() -> FieldSet:
    return FieldSet(name=_SCHEMA_NAME, fields=(Field(name="compound_id"), Field(name="value")))


def _value_mapper():
    """A monkeypatch for service.propose_mapping: returns a clear FieldMapping
    for each field the REDUCED field set asks about (novascreen -> potency/None)."""

    def _fn(table, field_set, client=None, *, headers_only=False):
        return MappingProposal(
            source_columns=list(table.headers),
            field_mappings=[
                FieldMapping(
                    target_field=name,
                    source_column="potency" if name == "value" else None,
                    confidence=0.9, reasoning="claude filled the remainder",
                    needs_confirmation=False,
                )
                for name in field_set.field_names
            ],
        )

    return _fn


def _preset_ready_mappings():
    """A fully-clear mapping for novascreen_batch01 against the full preset --
    for the plain-upload (no map file) regression guard."""
    return [
        FieldMapping(target_field="compound_id", source_column="cmpd", confidence=1.0,
                     reasoning="exact", needs_confirmation=False),
        FieldMapping(target_field="assay_type", source_column="assay", confidence=1.0,
                     reasoning="exact", needs_confirmation=False),
        FieldMapping(target_field="value", source_column="potency", confidence=1.0,
                     reasoning="exact", needs_confirmation=False),
        FieldMapping(target_field="unit", source_column=None, confidence=1.0,
                     reasoning="confirmed", needs_confirmation=False, inferred_value="nM"),
        FieldMapping(target_field="target", source_column="target_gene", confidence=1.0,
                     reasoning="exact", needs_confirmation=False),
        FieldMapping(target_field="n_replicates", source_column="replicates", confidence=1.0,
                     reasoning="exact", needs_confirmation=False),
        FieldMapping(target_field="assay_date", source_column="date", confidence=1.0,
                     reasoning="exact", needs_confirmation=False),
    ]


def _make_client(profile_store, schema_store, user):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user, get_profile_store, get_schema_store

    app.dependency_overrides[get_profile_store] = lambda: profile_store
    app.dependency_overrides[get_schema_store] = lambda: schema_store
    app.dependency_overrides[get_current_user] = lambda: user

    from fastapi.testclient import TestClient

    return TestClient(app)


def _clear():
    from assayingest.api.app import app

    app.dependency_overrides.clear()


def _upload_with_map(client, envelope, *, schema_name=_SCHEMA_NAME, vendor="acme", field_set=None):
    field_set = field_set or _reconcile_field_set()
    with open(NOVASCREEN_01, "rb") as f:
        return client.post(
            "/api/upload",
            files={
                "file": ("novascreen_batch01.csv", f, "text/csv"),
                "map_file": ("map.json", json.dumps(envelope).encode(), "application/json"),
            },
            data={
                "field_set": json.dumps(field_set.to_dict()),
                "schema_name": schema_name,
                "vendor": vendor,
            },
        )


# --- Task 2: /api/upload optional map-file branch + verified-user gate --------


def test_upload_conflicting_map_file_returns_reconcile_question_and_mutates_nothing(tmp_path, monkeypatch, profile_store, schema_store):
    """RECON-02: a map file that disagrees with the master returns 200
    kind="reconcile_question" with the conflict list, retains the entry under
    upload_token (map_envelope + target_schema_name + vendor + tmp_path
    present), and augments NOTHING (augment deferred until resolve)."""
    from assayingest.api.state import registry

    store, schema_id = _promoted_store(schema_store, master_aliases={"value": [_alias("acme", "cmpd")]})
    envelope = _envelope({"compound_id": [_alias("acme", "cmpd")]})
    before = store.list_aliases_for(schema_id)

    def _explode(*a, **k):
        raise AssertionError("propose_mapping must NOT run on a conflict")

    monkeypatch.setattr(service, "propose_mapping", _explode)
    client = _make_client(profile_store, store, _verified_user())

    resp = _upload_with_map(client, envelope)
    body = resp.json()
    token = body.get("upload_token")
    entry = registry.get(token) if token else None
    _clear()

    assert resp.status_code == 200
    assert body["kind"] == "reconcile_question"
    assert body["schema_name"] == _SCHEMA_NAME
    assert body["vendor"] == "acme"
    assert body["conflicts"] == [
        {"vendor": "acme", "source_column": "cmpd",
         "master_field": "value", "map_file_field": "compound_id"},
    ]
    assert entry is not None
    assert entry.map_envelope == envelope
    assert entry.target_schema_name == _SCHEMA_NAME
    assert entry.vendor == "acme"
    assert entry.tmp_path is not None and Path(entry.tmp_path).exists()
    assert store.list_aliases_for(schema_id) == before  # nothing augmented


def test_upload_clean_map_file_augments_and_returns_mapping(monkeypatch, profile_store, schema_store):
    """RECON-01: a non-conflicting (novel) map file returns 200 kind="mapping"
    (a normal MappingResponse with an upload_token) AFTER augmenting the
    crosswalk -- the map file's novel alias is now present with from_map_file
    provenance."""
    store, schema_id = _promoted_store(schema_store)
    envelope = _envelope({"compound_id": [_alias("acme", "cmpd")]})
    monkeypatch.setattr(service, "propose_mapping", _value_mapper())
    client = _make_client(profile_store, store, _verified_user())

    resp = _upload_with_map(client, envelope)
    _clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "mapping"
    assert body["upload_token"]
    aliases = store.list_aliases_for(schema_id)
    assert ("acme", "cmpd") in {(a.vendor, a.source_column) for a in aliases}
    assert any(a.provenance_kind == "from_map_file" for a in aliases)


def test_upload_map_file_signed_out_is_401_and_mutates_nothing(monkeypatch, profile_store, schema_store):
    """D-08-05 gate (signed out): a map-file upload with get_current_user -> None
    returns 401 and augments/maps nothing -- the gate runs BEFORE any work."""
    store, schema_id = _promoted_store(schema_store)
    before = store.list_aliases_for(schema_id)

    def _explode(*a, **k):
        raise AssertionError("propose_mapping must NOT run when gated out")

    monkeypatch.setattr(service, "propose_mapping", _explode)
    client = _make_client(profile_store, store, None)

    resp = _upload_with_map(client, _envelope({"compound_id": [_alias("acme", "cmpd")]}))
    _clear()

    assert resp.status_code == 401
    assert store.list_aliases_for(schema_id) == before


def test_upload_map_file_unverified_is_403(monkeypatch, profile_store, schema_store):
    """D-08-05 gate (unverified): a signed-in but unverified user gets 403 --
    authenticated yet forbidden from the governed augment (mirrors
    require_verified_user's 401-vs-403 semantics)."""
    store, schema_id = _promoted_store(schema_store)

    def _explode(*a, **k):
        raise AssertionError("propose_mapping must NOT run when gated out")

    monkeypatch.setattr(service, "propose_mapping", _explode)
    client = _make_client(profile_store, store, _unverified_user())

    resp = _upload_with_map(client, _envelope({"compound_id": [_alias("acme", "cmpd")]}))
    _clear()

    assert resp.status_code == 403


def test_plain_upload_no_map_file_now_requires_sign_in(monkeypatch, profile_store, schema_store):
    """D-10-13/T-10-20 reverses the premise this test used to pin: a plain
    upload (no map file, no schema) with get_current_user -> None is now
    401, never a mapping -- there is no anonymous upload path at all, augment
    or otherwise. See the sibling test below for the signed-in regression
    guard the original coverage was really providing."""
    monkeypatch.setattr(
        service, "propose_mapping",
        lambda table, fs, client=None, **kw: MappingProposal(
            source_columns=table.headers, field_mappings=_preset_ready_mappings()
        ),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = _make_client(profile_store, schema_store, None)  # signed out

    field_set = load_field_set(PRESET)
    with open(NOVASCREEN_01, "rb") as f:
        resp = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", f, "text/csv")},
            data={"field_set": json.dumps(field_set.to_dict())},
        )
    _clear()

    assert resp.status_code == 401


def test_plain_upload_signed_in_no_map_file_returns_mapping(monkeypatch, profile_store, schema_store):
    """The regression guard the renamed test above used to provide, kept
    alive under an authenticated client: a plain upload (no map file, no
    schema) still returns kind="mapping" as today -- the augment gate never
    touches the ordinary upload contract, only the sign-in gate does."""
    monkeypatch.setattr(
        service, "propose_mapping",
        lambda table, fs, client=None, **kw: MappingProposal(
            source_columns=table.headers, field_mappings=_preset_ready_mappings()
        ),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = _make_client(profile_store, schema_store, _verified_user())

    field_set = load_field_set(PRESET)
    with open(NOVASCREEN_01, "rb") as f:
        resp = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", f, "text/csv")},
            data={"field_set": json.dumps(field_set.to_dict())},
        )
    _clear()

    assert resp.status_code == 200
    assert resp.json()["kind"] == "mapping"


# --- Task 3: POST /api/reconcile/resolve two-step + confirm-gate intact -------


def _resolve(client, token, choices):
    return client.post(
        "/api/reconcile/resolve",
        json={"upload_token": token, "choices": choices},
    )


def test_reconcile_resolve_take_map_file_returns_mapping_and_cleans_up(tmp_path, monkeypatch, profile_store, schema_store):
    """RECON-02 resolve -> RECON-03: after a reconcile_question upload,
    /api/reconcile/resolve with take_map_file returns 200 kind="mapping" whose
    conflicting column reflects the human's choice (the map file's canonical
    field), and the retained temp file is cleaned up on resolve."""
    from assayingest.api.state import registry

    store, schema_id = _promoted_store(schema_store, master_aliases={"value": [_alias("acme", "cmpd")]})
    envelope = _envelope({"compound_id": [_alias("acme", "cmpd")]})
    monkeypatch.setattr(service, "propose_mapping", _value_mapper())
    client = _make_client(profile_store, store, _verified_user())

    up = _upload_with_map(client, envelope)
    assert up.json()["kind"] == "reconcile_question"
    token = up.json()["upload_token"]
    retained_tmp = registry.get(token).tmp_path

    resp = _resolve(
        client, token,
        [{"vendor": "acme", "source_column": "cmpd", "decision": "take_map_file"}],
    )
    _clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "mapping"
    by_field = {m["target_field"]: m for m in body["field_mappings"]}
    # take_map_file -> compound_id pre-fills to the map file's canonical field.
    assert by_field["compound_id"]["source_column"] == "cmpd"
    assert by_field["compound_id"]["confidence"] == 1.0
    assert not Path(retained_tmp).exists()  # temp file cleaned up on resolve


def test_reconcile_resolve_keep_master_prefills_master_field(monkeypatch, profile_store, schema_store):
    """The mirror run: keep_master pre-fills the conflicting column to the
    master's stored canonical field (value), not the map file's."""
    store, schema_id = _promoted_store(schema_store, master_aliases={"value": [_alias("acme", "cmpd")]})
    envelope = _envelope({"compound_id": [_alias("acme", "cmpd")]})
    monkeypatch.setattr(service, "propose_mapping", _value_mapper())
    client = _make_client(profile_store, store, _verified_user())

    up = _upload_with_map(client, envelope)
    token = up.json()["upload_token"]

    resp = _resolve(
        client, token,
        [{"vendor": "acme", "source_column": "cmpd", "decision": "keep_master"}],
    )
    _clear()

    assert resp.status_code == 200
    by_field = {m["target_field"]: m for m in resp.json()["field_mappings"]}
    assert by_field["value"]["source_column"] == "cmpd"
    assert by_field["value"]["confidence"] == 1.0


def test_reconcile_resolve_signed_out_is_401(profile_store, schema_store):
    """The resolve ALWAYS augments governed state, so it is unconditionally
    verified-user gated: a signed-out request is 401 before any registry work."""
    store, _ = _promoted_store(schema_store)
    client = _make_client(profile_store, store, None)

    resp = _resolve(client, "any-token", [])
    _clear()

    assert resp.status_code == 401


def test_reconcile_resolve_unverified_is_403(profile_store, schema_store):
    """A signed-in but unverified user is 403 on resolve (authenticated yet
    forbidden from the governed augment)."""
    store, _ = _promoted_store(schema_store)
    client = _make_client(profile_store, store, _unverified_user())

    resp = _resolve(client, "any-token", [])
    _clear()

    assert resp.status_code == 403


def test_reconcile_resolve_unknown_token_is_404(profile_store, schema_store):
    """A stale/unknown upload_token has no retained pending reconcile -> 404,
    nothing mutated."""
    store, schema_id = _promoted_store(schema_store)
    before = store.list_aliases_for(schema_id)
    client = _make_client(profile_store, store, _verified_user())

    resp = _resolve(
        client, "no-such-token",
        [{"vendor": "acme", "source_column": "cmpd", "decision": "keep_master"}],
    )
    _clear()

    assert resp.status_code == 404
    assert store.list_aliases_for(schema_id) == before


def test_reconciled_mapping_feeds_the_unchanged_confirm_gate(monkeypatch, profile_store, schema_store):
    """RECON-03: the reconciled proposal is an ORDINARY MappingProposal -- its
    upload_token feeds the EXISTING /api/confirm gate unchanged, and a
    fully-clear reconciled mapping confirms 200 (the server-side gate holds)."""
    store, schema_id = _promoted_store(schema_store, master_aliases={"value": [_alias("acme", "cmpd")]})
    envelope = _envelope({"compound_id": [_alias("acme", "cmpd")]})
    monkeypatch.setattr(service, "propose_mapping", _value_mapper())
    client = _make_client(profile_store, store, _verified_user())

    up = _upload_with_map(client, envelope)
    token = up.json()["upload_token"]
    resolved = _resolve(
        client, token,
        [{"vendor": "acme", "source_column": "cmpd", "decision": "take_map_file"}],
    ).json()
    assert resolved["kind"] == "mapping"
    confirm_token = resolved["upload_token"]

    field_mappings = [
        {
            k: m[k]
            for k in (
                "target_field", "source_column", "confidence", "reasoning",
                "needs_confirmation", "inferred_value", "alternatives",
            )
        }
        for m in resolved["field_mappings"]
    ]
    resp = client.post(
        "/api/confirm",
        json={
            "upload_token": confirm_token,
            "vendor": "test-vendor",
            "field_set": _reconcile_field_set().to_dict(),
            "field_mappings": field_mappings,
        },
    )
    _clear()

    assert resp.status_code == 200
    assert resp.json()["ready"] is True
