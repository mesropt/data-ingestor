"""POST /api/confirm -- the server-side P1 gate (API-02): the route's ONLY
job is deserialize -> `service.confirm(...)` -> map result/exception to HTTP
(PATTERNS.md confirm.py analog: `reconstruct.py`'s "build fresh, do not
copy an already-validated flag"). The gate itself -- rebuild a FRESH
`MappingProposal` from the human's edited column choices, re-run
`validate()`, read `is_ready` off the freshly-built object -- already lives
in `service.confirm` (04-01); this module never re-implements it, and never
reads `needs_confirmation`/`ready`/`is_ready` off the request body for any
decision.

The original `RawTable` is looked up from `api.state.registry` by
`upload_token`, NEVER rebuilt from anything the client sends (Server-Side
Gate table, RESEARCH.md) -- `ConfirmRequest` (api/wire.py) has no
`headers`/`source_columns`/`signature` field at all, so there is nothing for
a tampered client to send that could substitute for the retained table.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ... import service
from ...domain.models import ColumnCandidate, FieldMapping
from ...fields.loader import from_dict
from ..deps import get_profile_store
from ..state import registry
from ..wire import ConfirmFieldMappingIn, ConfirmRequest, ConfirmResponse

router = APIRouter()

#: Where a confirmed run's exported files live, keyed by `run_id` -- a
#: sibling of `_DEFAULT_DB_PATH` (".assayingest/profiles.db"), same
#: gitignored `/.assayingest/` directory (P2, local-only). `api/routes/
#: export.py` (Task 3) serves files from here; nothing else writes here.
EXPORT_BASE_DIR = Path(".assayingest/exports")


@router.post("/api/confirm")
def confirm(body: ConfirmRequest, store=Depends(get_profile_store)) -> ConfirmResponse:
    entry = registry.get(body.upload_token)
    if entry is None or entry.table is None:
        raise HTTPException(
            status_code=404,
            detail=f"no pending upload for token '{body.upload_token}'",
        )

    try:
        field_set = from_dict(body.field_set)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    edited_mappings = [_to_domain_mapping(m) for m in body.field_mappings]

    try:
        result = service.confirm(
            entry.table, edited_mappings, field_set,
            save_profile=body.save_profile, store=store, provenance=body.provenance,
        )
    except service.FieldCoverageError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "missing_fields": exc.missing_fields,
                "unknown_fields": exc.unknown_fields,
            },
        ) from exc
    except service.NotReadyError as exc:
        raise HTTPException(
            status_code=422,
            detail={"unclear_fields": [m.target_field for m in exc.unclear_fields]},
        ) from exc

    export_urls = None
    if body.export:
        run_id = str(uuid.uuid4())
        service.export(
            EXPORT_BASE_DIR / run_id, entry.table, field_set,
            result.proposal, result.tidy, body.provenance, "strict",
        )
        export_urls = _export_urls(run_id)

    return ConfirmResponse(
        ready=True, manifest=result.manifest, profile_id=result.profile_id,
        export=export_urls,
    )


def _to_domain_mapping(wire: ConfirmFieldMappingIn) -> FieldMapping:
    """The wire (edited field mapping) -> domain (`FieldMapping`) boundary
    translator. `needs_confirmation` is carried through as-is -- it is only
    ever the FRESH proposal's starting point; `service.confirm`'s own
    `validate()` call is what may OR a real violation back in, never this
    function (P1 lives in `validate()`, not here)."""
    return FieldMapping(
        target_field=wire.target_field,
        source_column=wire.source_column,
        confidence=wire.confidence,
        reasoning=wire.reasoning,
        needs_confirmation=wire.needs_confirmation,
        inferred_value=wire.inferred_value,
        alternatives=[
            ColumnCandidate(source_column=a.source_column, confidence=a.confidence)
            for a in wire.alternatives
        ],
    )


def _export_urls(run_id: str) -> dict[str, str]:
    return {
        "csv_url": f"/api/export/{run_id}/csv",
        "xlsx_url": f"/api/export/{run_id}/xlsx",
        "json_url": f"/api/export/{run_id}/json",
        "manifest_url": f"/api/export/{run_id}/manifest",
    }
