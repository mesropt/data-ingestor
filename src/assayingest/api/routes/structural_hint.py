"""POST /api/structural-hint/resolve (UI-02, D-04, W1) -- re-parse the
retained upload with the human's hint and return the SAME discriminated
shape `/api/upload` does (`kind="mapping"` or `kind="structural_question"`,
Pattern 5): a re-submitted hint can itself still be ambiguous.

W1: this route calls `service.resolve_or_map` -- never `cli._enrich_question`/
`parsing.structure_assist.propose_structure` (CLI-only, per Plan 01). The
API therefore has NO Claude structural-enrichment call site on this path at
all: there is no evidence-row-to-Claude leak vector to guard here by
construction, unlike the mapping path's `headers_only` toggle (tested in
Plan 02 Task 2), which this route still honors when a hint resolves straight
to a mapping.

D-10-13/T-10-22: gated by `require_user` -- a signed-out client must not be
able to drive a RETAINED upload to completion via this route either, even
though the route itself has no Claude call site. Closing only `/api/upload`
would leave this continuation open.
"""

from __future__ import annotations

import os

import anthropic
from fastapi import APIRouter, Depends, HTTPException

from ... import service
from ...auth.models import User
from ...parsing.hint import StructuralHint, StructureQuestion, TableShape
from ..deps import get_anthropic_client, get_profile_store, require_user
from ..state import UploadEntry, registry
from ..wire import MappingResponse, StructuralHintIn, StructuralHintResolveRequest, StructuralQuestionResponse

router = APIRouter()


@router.post("/api/structural-hint/resolve")
def resolve_structural_hint(
    body: StructuralHintResolveRequest,
    store=Depends(get_profile_store),
    client=Depends(get_anthropic_client),
    # D-10-13: a gate only, not a value this route reads -- the dependency's
    # sole job is to raise 401 for a signed-out request.
    user: User = Depends(require_user),
):
    entry = registry.pop(body.upload_token)
    if entry is None or entry.tmp_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"no pending structural question for token '{body.upload_token}'",
        )

    hint = _to_domain_hint(body.hint)

    try:
        result = service.resolve_or_map(
            entry.tmp_path, entry.field_set,
            store=store, hint=hint, headers_only=entry.headers_only, client=client,
        )
    except service.MissingCredentialsError as exc:
        _unlink_ignoring_missing(entry.tmp_path)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except anthropic.AuthenticationError as exc:
        _unlink_ignoring_missing(entry.tmp_path)
        raise HTTPException(
            status_code=401, detail="Anthropic rejected the credentials."
        ) from exc
    except (anthropic.APIError, ValueError) as exc:
        # CR-03/P2: a ValueError here is this route's NORMAL failure mode
        # (a re-submitted hint that still doesn't resolve a broken parse),
        # not an edge case -- `entry` was already popped from the registry
        # above, so this is the last remaining reference to the retained
        # temp file (uploaded cell values). Every error branch must unlink
        # it, mirroring upload.py's own error-path cleanup.
        _unlink_ignoring_missing(entry.tmp_path)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if isinstance(result, StructureQuestion):
        # Still ambiguous (Pattern 5) -- keep the SAME temp file alive under
        # a fresh token for a further resolve attempt.
        token = registry.put(
            UploadEntry(
                field_set=entry.field_set, headers_only=entry.headers_only,
                tmp_path=entry.tmp_path, source_file_name=entry.source_file_name,
            )
        )
        return StructuralQuestionResponse.from_question(result, token)

    # Resolved to a mapping (P2): the parsed RawTable is all the rest of the
    # flow needs -- the original file's bytes leave disk now, mirroring
    # /api/upload's own happy-path cleanup.
    token = registry.put(
        UploadEntry(
            field_set=entry.field_set, headers_only=entry.headers_only,
            tmp_path=None, table=result.table, provenance=result.provenance,
            source_file_name=entry.source_file_name,
        )
    )
    os.unlink(entry.tmp_path)
    return MappingResponse.from_proposal(
        result.proposal, result.provenance, token, source_name=entry.source_file_name
    )


def _unlink_ignoring_missing(path: str) -> None:
    """CR-03/P2: remove a retained temp file, tolerating a path that is
    already gone (e.g. a concurrent cleanup) -- a missing file at unlink
    time is not itself a bug worth surfacing; a file left behind is."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _to_domain_hint(wire: StructuralHintIn) -> StructuralHint:
    return StructuralHint(
        sheet_name=wire.sheet_name,
        header_row_index=wire.header_row_index,
        delimiter=wire.delimiter,
        decimal_separator=wire.decimal_separator,
        data_region=wire.data_region,
        table_shape=TableShape(wire.table_shape) if wire.table_shape is not None else None,
    )
