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
a tampered client to send that could substitute for the retained table. The
human's per-column date order (D-10-08) joins the retained table under the
exact same rule: it is read ONLY from `entry.date_answers`, never rebuilt
from anything `body` carries -- `ConfirmRequest` has no date field at all.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ... import service
from ...auth.models import User
from ...domain.models import ColumnCandidate, FieldMapping
from ...fields.loader import from_dict
from ..deps import get_profile_store, get_schema_store, require_verified_user
from ..state import registry
from ..wire import ConfirmFieldMappingIn, ConfirmRequest, ConfirmResponse

router = APIRouter()

#: Where a confirmed run's exported files live, keyed by `run_id` -- in the
#: gitignored `/.assayingest/` directory (P2, local-only). Persistence moved to
#: PostgreSQL, but this directory did NOT go with it: exports are files a curator
#: downloads, not rows. `api/routes/export.py` serves files from here; nothing else
#: writes here.
EXPORT_BASE_DIR = Path(".assayingest/exports")


@router.post("/api/confirm")
def confirm(
    body: ConfirmRequest,
    store=Depends(get_profile_store),
    schema_store=Depends(get_schema_store),
    user: User = Depends(require_verified_user),
) -> ConfirmResponse:
    # D-06-06: the server-side auth gate runs FIRST -- `require_verified_user`
    # raises 401 (signed out) / 403 (unverified) before any registry/gate work,
    # so an unauthenticated request never reaches the confirm logic below. The
    # attribution identity (AUTH-04) is taken from the server-resolved `user`,
    # never a client body field (T-06-07).
    entry = registry.get(body.upload_token)
    if entry is None or entry.table is None or entry.field_set is None:
        raise HTTPException(
            status_code=404,
            detail=f"no pending upload for token '{body.upload_token}'",
        )

    # CR-01: the RETAINED field set (the one the upload was actually
    # resolved against) is the sole authority for validation and assembly
    # -- body.field_set is never trusted for the gate itself. It is parsed
    # only to prove the client still agrees with what the server retained:
    # any drift at all (e.g. a dropped `min` constraint) is rejected
    # outright, never silently substituted for entry.field_set.
    try:
        submitted_field_set = from_dict(body.field_set)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if submitted_field_set.signature != entry.field_set.signature:
        raise HTTPException(
            status_code=422,
            detail="field set does not match the uploaded file",
        )
    field_set = entry.field_set

    # WR-04: the RETAINED provenance (the real "fresh-claude" or
    # "auto-applied-from-profile" branch the API itself took at
    # upload/resolve time) is the sole authority for the audit manifest --
    # body.provenance is a free-form client string and is never trusted for
    # it. `entry.provenance` is only ever unset here for an entry seeded
    # outside the real upload/resolve flow (never on the real path, since
    # `entry.table` being non-`None` above already proves a mapping
    # resolved), so the fallback below is a defensive default, not a
    # trust boundary.
    provenance = entry.provenance if entry.provenance is not None else "fresh-claude"

    edited_mappings = [_to_domain_mapping(m) for m in body.field_mappings]

    try:
        result = service.confirm(
            entry.table, edited_mappings, field_set,
            save_profile=body.save_profile, store=store, provenance=provenance,
            confirmed_by=user.email,
            # ALIAS-04: accrete the crosswalk from this same confirm. The alias
            # actor flows from the server-resolved user.email (AUTH-04), never a
            # body field (T-07-10); schema_name/vendor are the only client-
            # supplied labels, and the service records nothing unless BOTH are
            # present (mirrors Task 1's "absent = nothing written").
            schema_store=schema_store,
            target_schema_name=body.schema_name,
            vendor=body.vendor,
            # D-10-08/INGEST-04: the human's per-column date ORDER, read ONLY
            # from the RETAINED entry -- never from `body`, which carries no
            # date field of any kind (T-10-30). `service.confirm` re-derives
            # the concrete format itself from this and the retained table.
            date_answers=entry.date_answers,
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
    except service.UnresolvedDateColumnsError as exc:
        # Only reachable if a human re-points a date field at a DIFFERENT,
        # still-ambiguous column after already resolving the original one --
        # fail closed rather than guess (D-10-07/D-10-08).
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    export_urls = None
    if body.export:
        run_id = str(uuid.uuid4())
        service.export(
            EXPORT_BASE_DIR / run_id, entry.table, field_set,
            result.proposal, result.tidy, provenance, "strict",
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
