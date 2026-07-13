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
from assayingest.parsing.hint import StructuralHint, StructureQuestion
from assayingest.parsing.table import RawTable, parse_file
from assayingest.validation.validator import validate

from .conftest import verified_user

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


def test_upload_happy_path_returns_mapping_kind_with_upload_token(monkeypatch, profile_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user, get_profile_store

    monkeypatch.setattr(
        service, "propose_mapping",
        lambda table, fs, client=None, **kw: MappingProposal(
            source_columns=table.headers, field_mappings=_ready_field_mappings()
        ),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    field_set = load_field_set(PRESET)
    store = profile_store
    app.dependency_overrides[get_profile_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: verified_user()
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


def test_upload_mapping_response_names_the_source_file(monkeypatch, profile_store):
    """The Review screen shows the SOURCE FILE'S NAME, never the raw upload
    token (quick 260712) -- so the mapping response must carry the ORIGINAL
    client filename, not the tempfile's name the parser saw."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user, get_profile_store

    monkeypatch.setattr(
        service, "propose_mapping",
        lambda table, fs, client=None, **kw: MappingProposal(
            source_columns=table.headers, field_mappings=_ready_field_mappings()
        ),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    field_set = load_field_set(PRESET)
    app.dependency_overrides[get_profile_store] = lambda: profile_store
    app.dependency_overrides[get_current_user] = lambda: verified_user()
    client = TestClient(app)

    with open(NOVASCREEN_01, "rb") as f:
        response = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", f, "text/csv")},
            data={"field_set": json.dumps(field_set.to_dict())},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["source_name"] == "novascreen_batch01.csv"


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


def test_dependency_seams_are_overridable_and_auto_apply_reaches_a_tmp_path_store(profile_store):
    """get_profile_store/get_field_set_store/get_anthropic_client are
    overridable via app.dependency_overrides -- proven by injecting a
    tmp-path SqliteProfileStore that already holds a matching profile: the
    auto-apply branch reaches it with zero Anthropic client construction and
    zero credentials configured (mirrors service.py's own
    no-client/no-credentials-on-hit invariant, RESEARCH.md Pitfall 3)."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user, get_profile_store

    field_set = load_field_set(PRESET)
    table = parse_file(NOVASCREEN_01)
    store = profile_store
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
    app.dependency_overrides[get_current_user] = lambda: verified_user()
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


def test_upload_returns_structural_question_and_retains_temp_file(monkeypatch, tmp_path, profile_store):
    """UI-02, W1: a structurally-ambiguous upload returns the DETERMINISTIC
    parser's `StructureQuestion` unchanged -- the API has no Claude
    structural-enrichment call site. The temp file is retained (keyed by
    upload_token) so a future /api/structural-hint/resolve (Plan 03) can
    re-parse it -- P2's happy-path cleanup does NOT apply here."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user, get_profile_store
    from assayingest.api.state import registry

    question = StructureQuestion(
        unsure_about="which row is the real header",
        reason="no candidate header row scored clearly ahead of the others",
        confidence=0.5,
        proposal=StructuralHint(header_row_index=0),
        evidence_rows=[["a", "b"]],
    )
    monkeypatch.setattr(service, "resolve_or_map", lambda *a, **kw: question)

    store = profile_store
    app.dependency_overrides[get_profile_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: verified_user()
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


def test_upload_headers_only_reaches_the_real_mapper_with_no_cell_values(monkeypatch, profile_store):
    """P2 -- the REAL privacy guard: with `headers_only=true`, the actual
    (not monkeypatched) `propose_mapping`/`_render_table` chain runs against
    a fake Anthropic client injected via the `get_anthropic_client` DI seam,
    proving no cell value reaches the outbound Claude request at the HTTP
    boundary -- mirrors `tests/test_headers_only.py`'s
    `_FakeClient`/`_FakeMessages` idiom, one layer up."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_anthropic_client, get_current_user, get_profile_store

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
    store = profile_store
    app.dependency_overrides[get_profile_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: verified_user()
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


def test_upload_deletes_temp_file_on_the_happy_path(monkeypatch, profile_store):
    """P2/T-04-06: the temp file the upload was written to no longer exists
    on disk once a mapping resolves -- the parsed RawTable (in memory) is
    all the rest of the flow needs."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user, get_profile_store

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
    store = profile_store
    app.dependency_overrides[get_profile_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: verified_user()
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


def test_upload_rejects_disallowed_extension_before_parsing(profile_store):
    """T-04-04/T-04-05: a `.txt` upload is rejected before any bytes reach
    `parse()` -- the extension allowlist mirrors `parsing/table.py`'s own
    `.csv`/`.xlsx`/`.xls` set."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user, get_profile_store

    store = profile_store
    app.dependency_overrides[get_profile_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: verified_user()
    client = TestClient(app)

    field_set = load_field_set(PRESET)
    response = client.post(
        "/api/upload",
        files={"file": ("notes.txt", b"hello,world\n1,2\n", "text/plain")},
        data={"field_set": json.dumps(field_set.to_dict())},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 400


def test_upload_rejects_legacy_xls_with_a_400_not_a_500(profile_store):
    """WR-02: `.xls` was allow-listed at the upload boundary but
    `parsing/table.py` explicitly refuses it (the old binary format
    `openpyxl` cannot open) -- an upload was passing the allowlist, being
    written to a temp file, and then hitting `ValueError` deep inside
    `service.resolve_or_map`, surfacing as an HTTP 500 (a server error) for
    what is actually a client input error. `.xls` must be rejected at the
    allowlist itself, before any bytes reach `parse()`, with an actionable
    400."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user, get_profile_store

    store = profile_store
    app.dependency_overrides[get_profile_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: verified_user()
    client = TestClient(app)

    field_set = load_field_set(PRESET)
    response = client.post(
        "/api/upload",
        files={"file": ("legacy.xls", b"not a real xls file", "application/vnd.ms-excel")},
        data={"field_set": json.dumps(field_set.to_dict())},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "xlsx" in response.json()["detail"]


def test_upload_rejects_oversized_file(monkeypatch, profile_store):
    """T-04-05: an upload larger than the configured limit is rejected
    (413) via a bounded read, never buffered unbounded into memory/disk."""
    import assayingest.api.routes.upload as upload_module

    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user, get_profile_store

    monkeypatch.setattr(upload_module, "_MAX_UPLOAD_BYTES", 10)
    store = profile_store
    app.dependency_overrides[get_profile_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: verified_user()
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


def test_upload_never_uses_client_filename_as_a_path_component(monkeypatch, profile_store):
    """T-04-04: a filename like "../../etc/passwd.csv" never becomes a path
    component -- only its extension is used; the actual temp path is always
    tempfile-generated."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user, get_profile_store

    monkeypatch.setattr(
        service, "propose_mapping",
        lambda table, fs, client=None, **kw: MappingProposal(
            source_columns=table.headers, field_mappings=_ready_field_mappings()
        ),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    field_set = load_field_set(PRESET)
    store = profile_store
    app.dependency_overrides[get_profile_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: verified_user()
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


def test_second_same_signature_upload_auto_applies_with_no_second_claude_call(monkeypatch, profile_store):
    """SC4/API-03, the demo money shot: upload #1 (fresh-Claude) increments
    a spy on `service.propose_mapping` to 1; after a profile is saved
    directly into the injected store (simulating a curator's prior confirm
    -- no /api/confirm exists yet, Plan 03), upload #2 of the
    byte-identical-header sibling file auto-applies with zero yellow and
    the spy count stays at 1 -- no second Claude call."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user, get_profile_store

    field_set = load_field_set(PRESET)
    call_count = {"n": 0}

    def _spy_propose_mapping(table, fs, client=None, **kw):
        call_count["n"] += 1
        return MappingProposal(
            source_columns=table.headers, field_mappings=_ready_field_mappings()
        )

    monkeypatch.setattr(service, "propose_mapping", _spy_propose_mapping)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    store = profile_store
    app.dependency_overrides[get_profile_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: verified_user()
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


# --- Task 3: app.frontend() ordering + route-not-shadowed regression --------


def test_api_route_not_shadowed_by_frontend_fallback_when_dist_absent():
    """T-04-08: `/api/upload` is matched by the router, never by
    `app.frontend()`'s SPA catch-all -- even with `frontend/dist` absent
    (this checkout has no built bundle). A bare POST with no body is
    missing the required `file` field, so a 422 validation error FROM THE
    ROUTE proves the route was reached; a 404 or a 200 (an `index.html`
    fallback) would mean the frontend mount shadowed it instead. An
    authenticated client is injected so this test keeps proving what it was
    written to prove (route matching) rather than tripping the D-10-13
    sign-in gate first."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    app.dependency_overrides[get_current_user] = lambda: verified_user()
    client = TestClient(app)
    response = client.post("/api/upload")
    app.dependency_overrides.clear()

    assert response.status_code == 422


# --- SHAPE-04 at the HTTP boundary: the captured-outbound PAIR (12-05) --------
#
# D-12-06 names the hazard: the headers-only guarantee has NO central choke
# point -- it is enforced per call site, so every new Claude call site is a new
# place to get it wrong. This phase ADDED one (the layout judge, D-12-05), so
# this phase proves it at the OUTERMOST boundary: a fake client at the
# `get_anthropic_client` DI seam captures the ACTUAL outbound request through
# the REAL /api/upload -> describe_workbook -> judge_workbook_layout ->
# render_evidence_grid chain. Nothing in production is monkeypatched; only the
# SDK client is faked (the `:270` idiom above, one call site over).
#
# The two tests are a PAIR, and the second is not decoration. D-12-09 makes
# default-path realness a REQUIREMENT: the judge's strongest signal for a
# key-value layout is the real labels (`Patient Name`, `Accession #`), and a
# type-redacted grid throws them away. Without the mirror, a future
# over-zealous redaction would silently gut default-path accuracy with no test
# to catch it.

#: The phase's driving file (D-12-01): 8 sheets, and `Patient Info` is a real
#: key-value sheet whose cells are a real patient's identity.
CASCADE = (
    Path(__file__).resolve().parent.parent.parent
    / "data" / "synthetic" / "lab_corpus" / "cascade_allergy_CS-2026-698392.xlsx"
)
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: Real cell values from the real `Patient Info` grid -- a name, an accession
#: number, and a medical record number. The literals a curator flips the toggle
#: to protect. (`3809217` is a STRING cell in the file, not a number.)
_REAL_CELL_VALUES = ("TAYLOR, James", "CS-2026-698392", "3809217")


def _capturing_client() -> tuple[object, list[str]]:
    """A fake Anthropic client that records every outbound payload and answers
    nothing. `parsed_output=None` makes `judge_workbook_layout` raise (12-02's
    contract), which `_judge_or_unknown` degrades to all-UNKNOWN -- so the route
    still answers 200 and the privacy fact is provable regardless of what the
    judge concluded. Exactly the posture of the mapper's own privacy test above:
    the outbound content is captured BEFORE any downstream outcome."""
    captured: list[str] = []

    class _FakeMessages:
        def parse(self, **kwargs):
            captured.append(str(kwargs.get("system", "")))
            for message in kwargs.get("messages", []):
                captured.append(str(message.get("content", "")))

            class _Resp:
                parsed_output = None
                stop_reason = "end_turn"

            return _Resp()

    class _FakeClient:
        messages = _FakeMessages()

    return _FakeClient(), captured


def _upload_cascade(client, **data):
    with open(CASCADE, "rb") as fh:
        return client.post(
            "/api/upload",
            files={"file": (CASCADE.name, fh, _XLSX_MIME)},
            data=data,
        )


def _judging_upload(monkeypatch, profile_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_anthropic_client, get_current_user, get_profile_store

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake, captured = _capturing_client()
    app.dependency_overrides[get_profile_store] = lambda: profile_store
    app.dependency_overrides[get_current_user] = lambda: verified_user()
    app.dependency_overrides[get_anthropic_client] = lambda: fake
    return TestClient(app), captured


def test_upload_headers_only_judge_sends_no_cell_value(monkeypatch, profile_store):
    """SHAPE-04, PROVEN: with `headers_only=true`, not one real cell value of
    the cascade workbook appears in ANY outbound request the layout judge makes
    -- through the real chain, with only the SDK client faked. The evidence grid
    the model actually receives is type buckets (`str:med`, `num`, `blank`),
    never `TAYLOR, James`. `headers_only` is the curator's promise; a feature
    that lied here would be the worst failure a product selling honesty can
    have (D-12-11)."""
    from assayingest.api.app import app

    client, captured = _judging_upload(monkeypatch, profile_store)
    response = _upload_cascade(client, headers_only="true")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["kind"] == "sheet_question"  # the judge failed; the route still answers
    assert captured, "the judge made no outbound call at all -- nothing was proven"
    outbound = "\n".join(captured)
    for value in _REAL_CELL_VALUES:
        assert value not in outbound, value


def test_upload_default_judge_sends_the_real_grid(monkeypatch, profile_store):
    """THE MIRROR, and it is a requirement rather than a symmetry (D-12-09): on
    the DEFAULT path nothing is redacted for privacy's sake, because the real
    labels beside the real values are the single strongest signal a key-value
    layout has, and a type-redacted grid throws them away. Without this test, a
    future over-zealous redaction would silently degrade every default-path
    verdict with nothing to catch it.

    (It does NOT license the model to WRITE a value -- D-12-03/D-12-10 stands,
    and stands for the accuracy reason the builder ranks first: Python reads
    every value that ships.)"""
    from assayingest.api.app import app

    client, captured = _judging_upload(monkeypatch, profile_store)
    response = _upload_cascade(client, headers_only="false")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    outbound = "\n".join(captured)
    assert "TAYLOR, James" in outbound  # the REAL grid, by design
    assert "Patient Name" in outbound or "Name" in outbound
