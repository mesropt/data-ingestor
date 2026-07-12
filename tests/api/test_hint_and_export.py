"""POST /api/structural-hint/resolve (UI-02, P2) + GET /api/export/{run_id}/
{fmt} (EXPORT-02/03/04), TDD RED-first (04-03 Task 3).

The hint-resolve tests reuse `tests/test_hint_and_locale.py`'s own
"ambiguous decimal locale" CSV-construction idiom -- a genuinely
DETERMINISTIC parser ambiguity (D-14), resolved (or not) purely by
`parsing.table.parse()`'s own logic, never a Claude structural-enrichment
call (W1: this route has no such call site by construction).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from assayingest import service
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.models import Field, FieldSet


def _write_ambiguous_csv(tmp_path: Path) -> Path:
    """Every comma is followed by exactly 3 digits -- thousands grouping and
    a 3-decimal comma display are indistinguishable, so D-14 says ask
    (mirrors `tests/test_hint_and_locale.py::_write_ambiguous_csv`)."""
    csv = tmp_path / "ambiguous.csv"
    csv.write_text("Compound;Value\nA-1;1,234\nA-2;5,678\n", encoding="utf-8")
    return csv


def _client(profile_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_profile_store

    app.dependency_overrides[get_profile_store] = lambda: profile_store
    return TestClient(app)


def _seed_ambiguous_upload(tmp_path) -> tuple[str, str]:
    """Seeds the registry the same way `/api/upload` would have on the
    structural-question branch -- a real ambiguous CSV, its tmp_path
    retained, matching `tests/api/test_upload.py`'s own registry-reading
    idiom."""
    from assayingest.api.state import UploadEntry, registry

    csv_path = _write_ambiguous_csv(tmp_path)
    field_set = FieldSet(fields=(Field(name="compound_id"), Field(name="value")))
    token = registry.put(
        UploadEntry(field_set=field_set, headers_only=False, tmp_path=str(csv_path))
    )
    return token, str(csv_path)


# --- POST /api/structural-hint/resolve -----------------------------------------


def test_resolve_with_a_sufficient_hint_returns_mapping_kind_and_no_structural_enrichment(monkeypatch, tmp_path, profile_store):
    monkeypatch.setattr(
        service, "propose_mapping",
        lambda table, fs, client=None, **kw: MappingProposal(
            source_columns=table.headers,
            field_mappings=[
                FieldMapping(
                    target_field="compound_id", source_column="Compound",
                    confidence=1.0, reasoning="exact match", needs_confirmation=False,
                ),
                FieldMapping(
                    target_field="value", source_column="Value",
                    confidence=1.0, reasoning="exact match", needs_confirmation=False,
                ),
            ],
        ),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    token, csv_path = _seed_ambiguous_upload(tmp_path)
    client = _client(profile_store)

    response = client.post(
        "/api/structural-hint/resolve",
        json={"upload_token": token, "hint": {"decimal_separator": ","}},
    )
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "mapping"
    assert body["upload_token"] != token  # a fresh token for the resolved result
    # W1: the API never enriches with Claude on this path -- no
    # `parsing.structure_assist.propose_structure` call site exists here at
    # all (asserted structurally, not by monkeypatch spy -- see module docstring).
    assert not Path(csv_path).exists()  # happy path unlinks, mirrors /api/upload


def test_resolve_with_an_insufficient_hint_still_returns_structural_question(tmp_path, profile_store):
    """A re-submitted hint that does not answer the actual ambiguity (D-14)
    still returns the DETERMINISTIC `StructureQuestion`, unchanged, and
    retains the temp file for a further resolve attempt (Pattern 5)."""
    token, csv_path = _seed_ambiguous_upload(tmp_path)
    client = _client(profile_store)

    response = client.post(
        "/api/structural-hint/resolve",
        json={"upload_token": token, "hint": {}},
    )
    from assayingest.api.app import app
    from assayingest.api.state import registry

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "structural_question"
    assert "decimal locale" in body["unsure_about"]
    new_token = body["upload_token"]
    entry = registry.get(new_token)
    assert entry is not None
    assert entry.tmp_path == csv_path
    assert Path(csv_path).exists()  # retained -- not yet resolved


def test_resolve_unlinks_the_retained_temp_file_on_every_error_path(monkeypatch, tmp_path, profile_store):
    """CR-03/P2: a `ValueError` from a still-broken re-parse (this route's
    *normal* failure mode, not an edge case) must not leak the retained
    temp file -- it holds the uploaded assay/patient cell values.
    `entry` is popped from the registry up front, so this is the route's
    last chance to unlink it before the 500 response goes out."""
    monkeypatch.setattr(
        service, "resolve_or_map",
        lambda *a, **kw: (_ for _ in ()).throw(ValueError("still ambiguous, cannot resolve")),
    )

    token, csv_path = _seed_ambiguous_upload(tmp_path)
    client = _client(profile_store)

    response = client.post(
        "/api/structural-hint/resolve",
        json={"upload_token": token, "hint": {"decimal_separator": ","}},
    )
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 500
    assert not Path(csv_path).exists()  # CR-03: must not be leaked on the error path


def test_resolve_with_unknown_upload_token_returns_404(profile_store):
    client = _client(profile_store)

    response = client.post(
        "/api/structural-hint/resolve",
        json={"upload_token": "no-such-token", "hint": {}},
    )
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 404


# --- GET /api/export/{run_id}/{fmt} --------------------------------------------


def _write_export(run_id: str) -> None:
    """Seeds a confirmed run's exported files directly via `service.export`
    (04-01), the same writer `/api/confirm` (Task 2) calls -- exercising the
    download endpoint in isolation from the confirm gate."""
    from assayingest import canonical
    from assayingest.api.routes.confirm import EXPORT_BASE_DIR
    from assayingest.parsing.table import RawTable

    table = RawTable(
        headers=["cmpd", "potency"], rows=[["NVS-1", "12.5"]], source_name="batch.csv"
    )
    field_set = FieldSet(fields=(Field(name="compound_id"), Field(name="value")))
    proposal = MappingProposal(
        source_columns=table.headers,
        field_mappings=[
            FieldMapping(
                target_field="compound_id", source_column="cmpd", confidence=1.0,
                reasoning="exact match", needs_confirmation=False,
            ),
            FieldMapping(
                target_field="value", source_column="potency", confidence=1.0,
                reasoning="exact match", needs_confirmation=False,
            ),
        ],
    )
    tidy = canonical.assemble(table, proposal, field_set)
    service.export(
        EXPORT_BASE_DIR / run_id, table, field_set, proposal, tidy, "fresh-claude", "strict"
    )


def test_export_download_serves_all_four_formats_with_the_right_content_type(profile_store):
    client = _client(profile_store)
    run_id = "11111111-1111-1111-1111-111111111111"
    _write_export(run_id)

    expected_types = {
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "json": "application/json",
        "manifest": "application/json",
    }
    for fmt, content_type in expected_types.items():
        response = client.get(f"/api/export/{run_id}/{fmt}")
        assert response.status_code == 200, fmt
        assert response.headers["content-type"].startswith(content_type)

    from assayingest.api.app import app

    app.dependency_overrides.clear()


def test_export_download_unknown_run_id_returns_404(profile_store):
    client = _client(profile_store)
    response = client.get("/api/export/does-not-exist/csv")
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 404


def test_export_download_unknown_format_returns_404(profile_store):
    client = _client(profile_store)
    run_id = "22222222-2222-2222-2222-222222222222"
    _write_export(run_id)

    response = client.get(f"/api/export/{run_id}/pdf")
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 404


def test_export_download_rejects_a_path_traversal_run_id(profile_store):
    """T-04-13: `run_id` is never a client-controlled path -- only the exact
    `uuid.uuid4()` shape `confirm.py` ever mints is accepted; anything else
    (including a dot-segment-carrying value crafted to escape
    `EXPORT_BASE_DIR`) is rejected by the route's own regex guard with a 404
    before any filesystem access, never resolved as a path. (A literal `..`
    segment, or a `%2F`-encoded one, is normalised away by the HTTP client
    itself before the request is even sent -- this exercises the guard with
    a value that reaches the route unchanged.)"""
    client = _client(profile_store)
    response = client.get("/api/export/..sneaky-not-a-uuid/csv")
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 404
