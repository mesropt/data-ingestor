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


# --- Task 2: temp-file handling, discriminated response, auto-apply spy ------


def test_upload_returns_structural_question_and_retains_temp_file(monkeypatch, tmp_path):
    """UI-02, W1: a structurally-ambiguous upload returns the DETERMINISTIC
    parser's `StructureQuestion` unchanged -- the API has no Claude
    structural-enrichment call site. The temp file is retained (keyed by
    upload_token) so a future /api/structural-hint/resolve (Plan 03) can
    re-parse it -- P2's happy-path cleanup does NOT apply here."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_profile_store
    from assayingest.api.state import registry

    question = StructureQuestion(
        unsure_about="which row is the real header",
        reason="no candidate header row scored clearly ahead of the others",
        confidence=0.5,
        proposal=StructuralHint(header_row_index=0),
        evidence_rows=[["a", "b"]],
    )
    monkeypatch.setattr(service, "resolve_or_map", lambda *a, **kw: question)

    store = SqliteProfileStore(tmp_path / "profiles.db")
    app.dependency_overrides[get_profile_store] = lambda: store
    client = TestClient(app)

    with open(NOVASCREEN_01, "rb") as f:
        response = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", f, "text/csv")},
            data={"field_set": json.dumps(load_field_set(PRESET).to_dict())},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "structural_question"
    assert body["unsure_about"] == question.unsure_about
    assert body["answerable_by_hint"] is True
    assert body["upload_token"]

    entry = registry.get(body["upload_token"])
    assert entry is not None
    assert entry.tmp_path is not None
    assert Path(entry.tmp_path).exists()  # retained -- Plan 03's resolve re-parses it


def test_upload_headers_only_reaches_the_real_mapper_with_no_cell_values(
    monkeypatch, tmp_path
):
    """P2 -- the REAL privacy guard: with `headers_only=true`, the actual
    (not monkeypatched) `propose_mapping`/`_render_table` chain runs against
    a fake Anthropic client injected via the `get_anthropic_client` DI seam,
    proving no cell value reaches the outbound Claude request at the HTTP
    boundary -- mirrors `tests/test_headers_only.py`'s
    `_FakeClient`/`_FakeMessages` idiom, one layer up."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_anthropic_client, get_profile_store

    captured: dict = {}

    class _FakeMessages:
        def parse(self, **kwargs):
            captured["content"] = kwargs["messages"][0]["content"]

            class _Resp:
                parsed_output = None
                stop_reason = "end_turn"

            return _Resp()

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    field_set = FieldSet(fields=(Field(name="cmpd"), Field(name="potency")))
    store = SqliteProfileStore(tmp_path / "profiles.db")
    app.dependency_overrides[get_profile_store] = lambda: store
    app.dependency_overrides[get_anthropic_client] = lambda: _FakeClient()
    client = TestClient(app)

    with open(NOVASCREEN_01, "rb") as f:
        response = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", f, "text/csv")},
            data={"field_set": json.dumps(field_set.to_dict()), "headers_only": "true"},
        )
    app.dependency_overrides.clear()

    # The fake client's response carries no parsed_output, so the request
    # ultimately fails (mapped to 500) -- but the privacy guarantee is
    # provable regardless: the outbound content was already captured before
    # that failure.
    assert response.status_code == 500
    assert "12.5" not in captured["content"]  # a real cell value from batch01
    assert "NVS-0012" not in captured["content"]
    assert "cmpd" in captured["content"]


def test_upload_deletes_temp_file_on_the_happy_path(monkeypatch, tmp_path):
    """P2/T-04-06: the temp file the upload was written to no longer exists
    on disk once a mapping resolves -- the parsed RawTable (in memory) is
    all the rest of the flow needs."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_profile_store

    monkeypatch.setattr(
        service, "propose_mapping",
        lambda table, fs, client=None, **kw: MappingProposal(
            source_columns=table.headers, field_mappings=_ready_field_mappings()
        ),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    original_resolve_or_map = service.resolve_or_map
    captured_paths: list[str] = []

    def _spy(path, *a, **kw):
        captured_paths.append(path)
        return original_resolve_or_map(path, *a, **kw)

    monkeypatch.setattr(service, "resolve_or_map", _spy)

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
    assert captured_paths
    assert not Path(captured_paths[0]).exists()


def test_upload_rejects_disallowed_extension_before_parsing(tmp_path):
    """T-04-04/T-04-05: a `.txt` upload is rejected before any bytes reach
    `parse()` -- the extension allowlist mirrors `parsing/table.py`'s own
    `.csv`/`.xlsx`/`.xls` set."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_profile_store

    store = SqliteProfileStore(tmp_path / "profiles.db")
    app.dependency_overrides[get_profile_store] = lambda: store
    client = TestClient(app)

    field_set = load_field_set(PRESET)
    response = client.post(
        "/api/upload",
        files={"file": ("notes.txt", b"hello,world\n1,2\n", "text/plain")},
        data={"field_set": json.dumps(field_set.to_dict())},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 400


def test_upload_rejects_oversized_file(monkeypatch, tmp_path):
    """T-04-05: an upload larger than the configured limit is rejected
    (413) via a bounded read, never buffered unbounded into memory/disk."""
    import assayingest.api.routes.upload as upload_module

    from assayingest.api.app import app
    from assayingest.api.deps import get_profile_store

    monkeypatch.setattr(upload_module, "_MAX_UPLOAD_BYTES", 10)
    store = SqliteProfileStore(tmp_path / "profiles.db")
    app.dependency_overrides[get_profile_store] = lambda: store
    client = TestClient(app)

    field_set = load_field_set(PRESET)
    content = b"cmpd,value\n" + b"x" * 1000
    response = client.post(
        "/api/upload",
        files={"file": ("big.csv", content, "text/csv")},
        data={"field_set": json.dumps(field_set.to_dict())},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 413


def test_upload_never_uses_client_filename_as_a_path_component(monkeypatch, tmp_path):
    """T-04-04: a filename like "../../etc/passwd.csv" never becomes a path
    component -- only its extension is used; the actual temp path is always
    tempfile-generated."""
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
        content = f.read()
    response = client.post(
        "/api/upload",
        files={"file": ("../../etc/passwd.csv", content, "text/csv")},
        data={"field_set": json.dumps(field_set.to_dict())},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["kind"] == "mapping"
    assert not Path("/etc/passwd.csv").exists()


def test_second_same_signature_upload_auto_applies_with_no_second_claude_call(
    monkeypatch, tmp_path
):
    """SC4/API-03, the demo money shot: upload #1 (fresh-Claude) increments
    a spy on `service.propose_mapping` to 1; after a profile is saved
    directly into the injected store (simulating a curator's prior confirm
    -- no /api/confirm exists yet, Plan 03), upload #2 of the
    byte-identical-header sibling file auto-applies with zero yellow and
    the spy count stays at 1 -- no second Claude call."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_profile_store

    field_set = load_field_set(PRESET)
    call_count = {"n": 0}

    def _spy_propose_mapping(table, fs, client=None, **kw):
        call_count["n"] += 1
        return MappingProposal(
            source_columns=table.headers, field_mappings=_ready_field_mappings()
        )

    monkeypatch.setattr(service, "propose_mapping", _spy_propose_mapping)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    store = SqliteProfileStore(tmp_path / "profiles.db")
    app.dependency_overrides[get_profile_store] = lambda: store
    client = TestClient(app)

    with open(NOVASCREEN_01, "rb") as f:
        resp1 = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", f, "text/csv")},
            data={"field_set": json.dumps(field_set.to_dict())},
        )
    assert resp1.status_code == 200
    assert call_count["n"] == 1
    assert resp1.json()["kind"] == "mapping"

    table1 = parse_file(NOVASCREEN_01)
    profile = LearnedProfile(
        profile_id="api-money-shot",
        field_set_signature=field_set.signature,
        column_signature=column_signature(table1.headers),
        field_mappings=tuple(
            stored_mapping_from(m, table1.headers) for m in _ready_field_mappings()
        ),
        structural_hint=None,
        created_at="2026-01-01T00:00:00+00:00",
    )
    store.save(profile)

    with open(NOVASCREEN_02, "rb") as f:
        resp2 = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch02.csv", f, "text/csv")},
            data={"field_set": json.dumps(field_set.to_dict())},
        )
    app.dependency_overrides.clear()

    assert resp2.status_code == 200
    assert call_count["n"] == 1  # UNCHANGED -- no second Claude call (SC4)
    body2 = resp2.json()
    assert body2["ready"] is True
    assert all(not m["needs_confirmation"] for m in body2["field_mappings"])
    assert body2["provenance"] == "auto-applied-from-profile"
