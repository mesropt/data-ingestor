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
from ..deps import get_anthropic_client, get_profile_store, get_schema_store, require_user
from ..state import UploadEntry, registry
from ..wire import (
    DateFormatQuestionResponse,
    MappingResponse,
    StructuralHintIn,
    StructuralHintResolveRequest,
    StructuralQuestionResponse,
)

router = APIRouter()


@router.post("/api/structural-hint/resolve")
def resolve_structural_hint(
    body: StructuralHintResolveRequest,
    store=Depends(get_profile_store),
    schema_store=Depends(get_schema_store),
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

    # 11-06/D-11-22: re-fetch the governed Schema by the RETAINED name,
    # exactly as date_format.py does -- `UploadEntry` retains only the name,
    # never the Schema object itself. Threading it (with the retained
    # `sheet` and `strictness`) into `resolve_or_map` restores everything
    # the direct `/api/upload` path already had here: the Python-first
    # crosswalk prefill (D-10-03), the escalation line, and (T-11-21) the
    # exact worksheet the human chose -- `parse(path, sheet=...)`
    # short-circuits sheet ranking, so the resolve can never re-rank the
    # workbook and silently map a different sheet's columns.
    schema = schema_store.get_schema(entry.schema_name) if entry.schema_name else None

    try:
        result = service.resolve_or_map(
            entry.tmp_path, entry.field_set,
            store=store, hint=hint, sheet=entry.sheet, strictness=entry.strictness,
            headers_only=entry.headers_only, client=client, schema=schema,
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
        # a fresh token for a further resolve attempt. The retained
        # schema/sheet/strictness context survives too (11-06): a SECOND
        # hint attempt must not re-enter the very hole this route just
        # climbed out of.
        token = registry.put(
            UploadEntry(
                field_set=entry.field_set, headers_only=entry.headers_only,
                tmp_path=entry.tmp_path, schema_name=entry.schema_name,
                sheet=entry.sheet, strictness=entry.strictness,
                source_file_name=entry.source_file_name,
            )
        )
        return StructuralQuestionResponse.from_question(result, token)

    if result.date_question.has_conflicts:
        # D-10-07 mirrored from /api/upload (11-06, quick 260712-qgc): an
        # ambiguous date column BEHIND the structural question must raise
        # the date question now, not come back as a mapping whose date field
        # is amber forever (Confirm 422s with no way out). Retain the
        # ALREADY-PARSED table + resolved proposal (tmp_path=None: nothing
        # is left to re-parse) so /api/date-format/resolve needs no re-parse
        # at all.
        token = registry.put(
            UploadEntry(
                field_set=entry.field_set, headers_only=entry.headers_only,
                tmp_path=None, table=result.table, provenance=result.provenance,
                proposal=result.proposal, schema_name=entry.schema_name,
                strictness=entry.strictness, escalation=result.escalation,
                source_file_name=entry.source_file_name,
            )
        )
        os.unlink(entry.tmp_path)
        return DateFormatQuestionResponse.from_question(
            result.date_question, token, headers_only=entry.headers_only
        )

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
    # 10-09/INGEST-02 mirrored from /api/upload (11-06): the remembered-vendor
    # lookup -- profile match, then crosswalk fallback, refusing to guess on
    # ambiguity. Without it the vendor box is empty after every structural
    # question, and /api/confirm REQUIRES a vendor (422 otherwise).
    vendor_memory = service.recall_vendor(result.table, entry.field_set, schema, store)
    return MappingResponse.from_proposal(
        result.proposal, result.provenance, token,
        escalation=result.escalation, vendor_memory=vendor_memory,
        source_name=entry.source_file_name,
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
