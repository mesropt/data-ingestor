"""POST /api/reconcile/resolve (D-08-02 step 2, D-08-03) -- continue a reconcile
AFTER the human has resolved its conflicts, returning the SAME discriminated
shape `/api/upload` does (`kind="mapping"` or, defensively, `"structural_question"`).

A PURE adapter over `service.apply_reconcile_resolution`, mirroring
`structural_hint.py`'s two-step structure exactly (D-08-03): pop the retained
entry (map envelope + target Schema + vendor + temp file) from the token
registry, map the wire choices to the service's `(vendor, source_column,
decision)` shape, call the seam, serialize whichever branch it returns, and
clean up the temp file on EVERY branch (success + all errors, T-08-10).

The resolve ALWAYS augments the governed master crosswalk, so it is
unconditionally verified-user gated via `require_verified_user` (D-08-05,
T-08-06) -- unlike the upload route's map-file branch, which must apply the
gate conditionally. The resolution logic (override from the human choice,
augment, pre-fill) all lives in `service.apply_reconcile_resolution` (08-01);
this route never re-implements it.
"""

from __future__ import annotations

import os

import anthropic
from fastapi import APIRouter, Depends, HTTPException

from ... import service
from ...auth.models import User
from ...parsing.hint import StructureQuestion
from ..deps import (
    get_anthropic_client,
    get_profile_store,
    get_schema_store,
    require_verified_user,
)
from ..state import UploadEntry, registry
from ..wire import MappingResponse, ReconcileResolveRequest, StructuralQuestionResponse

router = APIRouter()


@router.post("/api/reconcile/resolve")
def resolve_reconcile(
    body: ReconcileResolveRequest,
    store=Depends(get_profile_store),
    schema_store=Depends(get_schema_store),
    client=Depends(get_anthropic_client),
    user: User = Depends(require_verified_user),
):
    entry = registry.pop(body.upload_token)
    if entry is None or entry.tmp_path is None or entry.map_envelope is None:
        raise HTTPException(
            status_code=404,
            detail=f"no pending reconcile for token '{body.upload_token}'",
        )

    choices = [(c.vendor, c.source_column, c.decision) for c in body.choices]

    try:
        result = service.apply_reconcile_resolution(
            entry.tmp_path, entry.field_set,
            schema_store=schema_store, target_schema_name=entry.target_schema_name,
            vendor=entry.vendor, envelope=entry.map_envelope, choices=choices,
            store=store, headers_only=entry.headers_only, client=client,
        )
    except service.SchemaNotFoundError as exc:
        _unlink_ignoring_missing(entry.tmp_path)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.UnresolvedConflictsError as exc:
        # F2/P1: the human left a detected conflict undecided -- fail closed
        # rather than let the normalized index pick a side by row order. Nothing
        # was augmented or mapped (the guard runs before any mutation).
        _unlink_ignoring_missing(entry.tmp_path)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except service.MissingCredentialsError as exc:
        _unlink_ignoring_missing(entry.tmp_path)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except anthropic.AuthenticationError as exc:
        _unlink_ignoring_missing(entry.tmp_path)
        raise HTTPException(
            status_code=401, detail="Anthropic rejected the credentials."
        ) from exc
    except (anthropic.APIError, ValueError) as exc:
        # T-08-10/P2: `entry` was already popped above, so this is the last
        # remaining reference to the retained temp file (uploaded cell values).
        # Every error branch must unlink it, mirroring structural_hint.py.
        _unlink_ignoring_missing(entry.tmp_path)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if isinstance(result, StructureQuestion):
        # Defensive (Pattern 5): a re-parse could still be structurally
        # ambiguous -- keep the SAME temp file alive under a fresh token for a
        # further structural-hint resolve.
        token = registry.put(
            UploadEntry(
                field_set=entry.field_set, headers_only=entry.headers_only,
                tmp_path=entry.tmp_path,
            )
        )
        return StructuralQuestionResponse.from_question(result, token)

    # Resolved to a mapping (P2): the crosswalk was augmented and the parsed
    # RawTable is all the rest of the flow needs -- the temp file leaves disk
    # now, and the result lands in the SAME review UI under the unchanged
    # /api/confirm gate (RECON-03), mirroring structural_hint's success path.
    token = registry.put(
        UploadEntry(
            field_set=entry.field_set, headers_only=entry.headers_only,
            tmp_path=None, table=result.table, provenance=result.provenance,
        )
    )
    os.unlink(entry.tmp_path)
    return MappingResponse.from_proposal(result.proposal, result.provenance, token)


def _unlink_ignoring_missing(path: str) -> None:
    """T-08-10/P2: remove a retained temp file, tolerating a path already gone
    (a concurrent cleanup) -- a missing file at unlink time is not a bug worth
    surfacing; a file LEFT BEHIND is (mirrors structural_hint.py)."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
