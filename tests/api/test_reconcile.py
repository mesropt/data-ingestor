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
from assayingest.learning.sqlite_schema_store import SqliteSchemaStore
from assayingest.learning.sqlite_store import SqliteProfileStore

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


def test_upload_entry_without_retention_fields_still_constructs():
    """The new fields are purely additive -- an existing UploadEntry(...) call
    (no reconcile fields) still constructs, all three defaulting to None."""
    from assayingest.api.state import UploadEntry

    entry = UploadEntry(field_set=None, headers_only=False, tmp_path=None)
    assert entry.map_envelope is None
    assert entry.target_schema_name is None
    assert entry.vendor is None
