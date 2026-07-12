"""SC4: the browser money-shot, provable at the API level -- upload ->
confirm+save -> re-upload same signature yields zero yellow and exactly one
Claude call across both uploads (04-03 Task 3, TDD RED-first).

Reuses `tests/api/test_upload.py`'s exact fixture pair
(`novascreen_batch01.csv`/`novascreen_batch02.csv`) and
`_ready_field_mappings()` builder shape -- this is the full round-trip
`/api/upload` -> `/api/confirm` -> `/api/upload` sequence that test file's
own money-shot test could only half-prove (it seeded the profile directly,
since `/api/confirm` did not exist yet in Plan 02).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from assayingest import service
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.loader import load as load_field_set

from .conftest import verified_user

DATA = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic"
PRESET = Path(__file__).resolve().parent.parent.parent / "presets" / "assay-potency.yaml"
NOVASCREEN_01 = DATA / "novascreen_batch01.csv"
NOVASCREEN_02 = DATA / "novascreen_batch02.csv"


def _ready_field_mappings() -> list[FieldMapping]:
    """Mirrors `tests/api/test_upload.py::_ready_field_mappings` exactly
    (per-test-file helper duplication is this project's established
    convention, PATTERNS.md)."""
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


def test_upload_confirm_reupload_money_shot_zero_yellow_one_claude_call(monkeypatch, profile_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user, get_profile_store

    call_count = {"n": 0}

    def _spy_propose_mapping(table, fs, client=None, **kw):
        call_count["n"] += 1
        return MappingProposal(
            source_columns=table.headers, field_mappings=_ready_field_mappings()
        )

    monkeypatch.setattr(service, "propose_mapping", _spy_propose_mapping)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    field_set = load_field_set(PRESET)
    store = profile_store
    app.dependency_overrides[get_profile_store] = lambda: store
    # 06-02/10-09: /api/confirm is gated by require_verified_user and
    # /api/upload is now gated by require_user -- overriding get_current_user
    # (the single root dependency both are built on) satisfies both with one
    # seam, so the money-shot round-trip's upload AND confirm+save steps are
    # both allowed for this authenticated verified curator.
    app.dependency_overrides[get_current_user] = lambda: verified_user()
    client = TestClient(app)

    # 1. Upload lab X's first file -- fresh-Claude branch, spy -> 1.
    with open(NOVASCREEN_01, "rb") as f:
        upload1 = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", f, "text/csv")},
            data={"field_set": json.dumps(field_set.to_dict())},
        )
    assert upload1.status_code == 200
    assert call_count["n"] == 1
    body1 = upload1.json()
    assert body1["kind"] == "mapping"
    assert body1["ready"] is True
    assert all(not m["needs_confirmation"] for m in body1["field_mappings"])

    # 2. Confirm + save the profile -- the curator's one-time confirmation
    # (LEARN-02). Echoes the upload response's own field_mappings back --
    # ConfirmFieldMappingIn ignores the extra validator_note key it also
    # carries (Pydantic's default "ignore unknown fields" behavior).
    confirm = client.post(
        "/api/confirm",
        json={
            "upload_token": body1["upload_token"],
            "field_set": field_set.to_dict(),
            "field_mappings": body1["field_mappings"],
            "save_profile": True,
        },
    )
    assert confirm.status_code == 200
    assert confirm.json()["profile_id"] is not None

    # 3. Upload lab X's SECOND file (byte-identical headers) -- auto-apply
    # branch: zero yellow, zero SECOND Claude call (SC4, the whole point).
    with open(NOVASCREEN_02, "rb") as f:
        upload2 = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch02.csv", f, "text/csv")},
            data={"field_set": json.dumps(field_set.to_dict())},
        )
    app.dependency_overrides.clear()

    assert upload2.status_code == 200
    assert call_count["n"] == 1  # UNCHANGED -- the money shot
    body2 = upload2.json()
    assert body2["kind"] == "mapping"
    assert body2["ready"] is True
    assert body2["provenance"] == "auto-applied-from-profile"
    assert all(not m["needs_confirmation"] for m in body2["field_mappings"])
