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
from pathlib import Path

import anthropic
from fastapi import APIRouter, Depends, HTTPException

from ... import service
from ...auth.models import User
from ...parsing.hint import StructuralHint, StructureQuestion, TableShape
from ...parsing.structure.grid import list_worksheets
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
    # T-12-15 (ASVS V5): the wire model already refused every index that could
    # not be true of ANY grid (a negative column, an inverted range). This is
    # the SECOND closure, and it is not redundant: an index can be well-formed
    # and still be false of THIS file -- a stale payload, a tampered one, or a
    # hallucinated verdict a client replayed. Bounded against the real grid
    # BEFORE any allocation, so a `last_row` of a billion is a 422 in a moment,
    # never a memory-exhausting slice; and refused with the consequence, never
    # an `IndexError` from deep inside the un-pivot surfacing as a 500 (the
    # WR-02 bug class: a client input error dressed as a server error).
    try:
        _refuse_out_of_grid_indices(entry.tmp_path, entry.sheet, hint)
    except HTTPException:
        _unlink_ignoring_missing(entry.tmp_path)
        raise

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
            source_name=entry.source_file_name,
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
        # climbed out of. `group_id` survives the hop too (11-08, the 11-07
        # handoff): membership rides on the ENTRY, and a re-put that dropped
        # it would silently lose this member from its group's archive --
        # exactly the members that needed a question.
        token = registry.put(
            UploadEntry(
                field_set=entry.field_set, headers_only=entry.headers_only,
                tmp_path=entry.tmp_path, schema_name=entry.schema_name,
                sheet=entry.sheet, strictness=entry.strictness,
                source_file_name=entry.source_file_name,
                group_id=entry.group_id,
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
                # 11-08 (the 11-07 handoff): membership survives this hop too,
                # or the member vanishes from its group's archive at confirm.
                sheet=entry.sheet, group_id=entry.group_id,
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
            # 11-08 (the 11-07 handoff): a member whose hint resolves straight
            # to a mapping must reach Confirm still knowing whose member it is
            # -- `confirm.py` records its run into the group from these two
            # fields, and nothing else.
            sheet=entry.sheet, group_id=entry.group_id,
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
    """The human's answer, wire -> domain.

    `layout` is the round trip that makes `answerable_by_hint=True` finally
    mean something (D-12-15): the confirmed verdict re-enters `parse()`, which
    READS it -- a confirmed key-value answer un-pivots, a confirmed
    row-per-record answer reads from the named header row. `table_shape`, which
    this supersedes, was write-only (two writes, zero reads), which is exactly
    why the old shape question had to advertise itself as unanswerable."""
    return StructuralHint(
        sheet_name=wire.sheet_name,
        header_row_index=wire.header_row_index,
        delimiter=wire.delimiter,
        decimal_separator=wire.decimal_separator,
        data_region=wire.data_region,
        table_shape=TableShape(wire.table_shape) if wire.table_shape is not None else None,
        layout=wire.layout.to_domain() if wire.layout is not None else None,
    )


def _refuse_out_of_grid_indices(
    tmp_path: str, sheet: str | None, hint: StructuralHint
) -> None:
    """Refuse a client-posted layout whose indices do not exist in THIS file's
    grid -- a 422 naming the consequence, before a single row is allocated.

    Non-.xlsx files and an unreadable/unknown sheet are deliberately NOT judged
    here: `parse()` owns those errors and reports them with its own actionable
    message, and inventing a second, differently-worded verdict on the same
    broken file would be a worse answer, not a safer one.

    `parsing.table` carries its OWN guard on every verdict index (T-12-08,
    12-03) and keeps it: this route's check is the OUTER closure, where a client
    error can still be named as one. The inner guard exists because a verdict
    also arrives from the judge, which this route never sees."""
    if hint.layout is None or Path(tmp_path).suffix.lower() != ".xlsx":
        return
    try:
        worksheets = list_worksheets(tmp_path)
        target = next(
            (ws for ws in worksheets if ws.title == sheet),
            worksheets[0] if len(worksheets) == 1 else None,
        )
        if target is None:
            return  # parse() resolves (or refuses) the sheet; never pre-empted here
        rows = list(target.iter_rows(values_only=True))
    except Exception:
        return  # a broken workbook is parse()'s error to raise, verbatim

    height = len(rows)
    width = max((len(row) for row in rows), default=0)
    layout = hint.layout
    for index in (layout.header_row_index, layout.first_data_row, layout.last_data_row):
        if index is not None and index >= height:
            raise _out_of_grid_error(index, height, width)
    for block in layout.key_value_blocks:
        if block.last_row >= height or block.first_row >= height:
            raise _out_of_grid_error(max(block.first_row, block.last_row), height, width)
        for column in (block.label_column, *block.value_columns):
            if column >= width:
                raise _out_of_grid_error(column, height, width)


def _out_of_grid_error(index: int, height: int, width: int) -> HTTPException:
    """Consequence first (CLAUDE.md): name what did NOT happen, not the symptom
    -- mirrors `sheets.py::_validated_selections`' "Nothing was ingested:"
    shape, the same posture applied one route over."""
    return HTTPException(
        status_code=422,
        detail=(
            f"Nothing was ingested: the layout points at cell index {index}, "
            f"which is outside this sheet's {height} rows x {width} columns. "
            "Answer the layout question again against the sheet as it actually is."
        ),
    )
