"""SHEET-03/D-11-15: provenance reaches the DOWNLOADED file on EVERY ingest.

The decision this file pins is the uncomfortable half of SHEET-03: a
traceability column that only sometimes exists is not a traceability column.
So a plain CSV upload -- no worksheets at all -- must still carry
`__source_sheet` on every exported row, valued with the file the curator
actually chose.

The value is `table.origin_sheet or entry.source_file_name`, and NEVER
`RawTable.source_name`: on the API path the parser only ever saw a TEMPFILE's
generated name (`wire.py`'s own `source_name` docstring says so), so leaking
that into an export would be both useless to a human and an information
disclosure (T-11-09). `test_..._is_never_a_tempfile_name` is the guard.

Reuses `tests/api/test_money_shot.py`'s upload -> confirm round-trip and its
`propose_mapping` monkeypatch idiom (never a live Claude call).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from fastapi.testclient import TestClient

from assayingest import service
from assayingest.canonical import SOURCE_SHEET_COLUMN
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.loader import load as load_field_set

from .conftest import verified_user

DATA = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic"
PRESET = Path(__file__).resolve().parent.parent.parent / "presets" / "assay-potency.yaml"
NOVASCREEN_01 = DATA / "novascreen_batch01.csv"


def _ready_field_mappings() -> list[FieldMapping]:
    """Mirrors `tests/api/test_money_shot.py::_ready_field_mappings` exactly
    (per-test-file helper duplication is this project's convention)."""
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


def _confirm_a_csv_upload_and_export(monkeypatch, profile_store) -> str:
    """Upload novascreen_batch01.csv, confirm it with `export: true`, and
    return the minted `run_id` -- the real route path, end to end."""
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

    with open(NOVASCREEN_01, "rb") as fh:
        upload = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", fh, "text/csv")},
            data={"field_set": json.dumps(field_set.to_dict())},
        )
    assert upload.status_code == 200, upload.text
    body = upload.json()
    assert body["kind"] == "mapping"

    confirm = client.post(
        "/api/confirm",
        json={
            "upload_token": body["upload_token"],
            "vendor": "novascreen",
            "field_set": field_set.to_dict(),
            "field_mappings": body["field_mappings"],
            "export": True,
        },
    )
    app.dependency_overrides.clear()

    assert confirm.status_code == 200, confirm.text
    export_urls = confirm.json()["export"]
    assert export_urls is not None
    # "/api/export/{run_id}/csv" -> run_id
    return export_urls["csv_url"].split("/")[3]


def _export_dir(run_id: str) -> Path:
    from assayingest.api.routes.confirm import EXPORT_BASE_DIR

    return EXPORT_BASE_DIR / run_id


def test_a_confirmed_csv_export_carries_source_sheet_in_all_three_formats(
    monkeypatch, profile_store
):
    """D-11-15: a CSV has no worksheets, and still every exported row records
    where it came from -- in csv, xlsx AND json."""
    import openpyxl

    run_id = _confirm_a_csv_upload_and_export(monkeypatch, profile_store)
    out = _export_dir(run_id)

    with (out / "export.csv").open("r", newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0][-1] == SOURCE_SHEET_COLUMN
    assert len(rows) > 1
    assert all(row[-1] == "novascreen_batch01.csv" for row in rows[1:])

    xlsx_rows = list(
        openpyxl.load_workbook(out / "export.xlsx").active.iter_rows(values_only=True)
    )
    assert xlsx_rows[0][-1] == SOURCE_SHEET_COLUMN
    assert all(row[-1] == "novascreen_batch01.csv" for row in xlsx_rows[1:])

    records = json.loads((out / "export.json").read_text(encoding="utf-8"))
    assert records
    assert all(r[SOURCE_SHEET_COLUMN] == "novascreen_batch01.csv" for r in records)


def test_the_manifest_records_the_same_source_sheet_as_the_data(monkeypatch, profile_store):
    """The manifest is the audit trail: it must never disagree with the file
    it shipped alongside."""
    run_id = _confirm_a_csv_upload_and_export(monkeypatch, profile_store)
    manifest = json.loads(
        (_export_dir(run_id) / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["source_sheet"] == "novascreen_batch01.csv"


def test_the_exported_source_sheet_is_never_a_tempfile_name(monkeypatch, profile_store):
    """T-11-09: on the API path `RawTable.source_name` is a TEMPFILE's
    generated name -- writing it into an export would disclose a server path
    fragment and tell the curator nothing. The provenance must come from
    `origin_sheet` (a real worksheet title) or the client's own filename."""
    run_id = _confirm_a_csv_upload_and_export(monkeypatch, profile_store)
    records = json.loads(
        (_export_dir(run_id) / "export.json").read_text(encoding="utf-8")
    )

    for record in records:
        source = record[SOURCE_SHEET_COLUMN]
        assert source == "novascreen_batch01.csv"
        assert not source.startswith("tmp")
