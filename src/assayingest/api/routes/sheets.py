"""POST /api/sheets/resolve (SHEET-01/04/05, D-11-08) -- turn the human's
answer to the sheet question into N INDEPENDENT DATASETS.

NOTHING IS MERGED, ANYWHERE, and no affordance is left behind that could be
mistaken for a place to add it later. SHEET-02 is struck from the PRODUCT, not
deferred: N selected sheets produce N separate datasets, each with its own
Schema, its own mapping, its own amber gate, its own confirm and its own export.
There is no combining path in this file and no aggregate readiness anywhere on
its response.

THE RUN GROUP IS A GROUP ID OWNING N ORDINARY `upload_token`s (D-11-20, Option
A), and that is why this whole feature costs the rest of the codebase nothing:
`service.confirm`, `service.export`, `_is_review_ready`, the `pending_uploads`
round-trip, `GET /api/export/{run_id}/{fmt}`, `MappingResponse` and
`date_format.py` are all UNTOUCHED by it. Every member is an ordinary upload
that happens to know which group it belongs to. Widening `UploadEntry` to hold N
tables instead would have broken all eight.

Each selected sheet is re-parsed with an explicit `sheet=`, which
short-circuits sheet ranking (`table.py`) and runs THAT sheet's own full gate
chain -- header row, table shape, decimal locale, date order. That is how
SHEET-04 comes for free: a selected sheet that fails a gate raises its OWN
question, in its OWN member, instead of being dropped. It is also why each sheet
resolves its own date order for itself, and why a disagreement BETWEEN sheets is
no longer a contradiction to surface (D-11-09) -- they are separate datasets, and
separate datasets are entitled to disagree.

Temp-file lifecycle (T-11-24, Pitfall 3): every question-bearing member gets its
OWN COPY of the workbook. `/api/structural-hint/resolve` unlinks
`entry.tmp_path` on success and on every error branch, and the registry unlinks
on eviction -- so if two members shared one path, the first resolve would delete
the file out from under the second. A per-member copy means every one of those
existing unlink rules stays correct with ZERO changes, and the registry remains
the one place a temp file's lifecycle is fully owned. Refcounting a shared path
was rejected for putting a second, subtler owner beside it.

D-10-13/T-11-23: gated by `require_user`, exactly as `/api/upload`,
`/api/structural-hint/resolve` and `/api/date-format/resolve` are. Closing the
upload alone would leave this CONTINUATION open -- a signed-out client must not
be able to drive a retained workbook to completion here either.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import anthropic
from fastapi import APIRouter, Depends, HTTPException

from ... import service
from ...auth.models import User
from ...domain.models import Schema
from ...parsing.hint import StructureQuestion
from ..deps import get_anthropic_client, get_profile_store, get_schema_store, require_user
from ..state import UploadEntry, UploadGroup, groups, registry
from ..wire import (
    DateFormatQuestionResponse,
    MappingResponse,
    SheetGroupResponse,
    SheetMemberOut,
    SheetResolveRequest,
    SheetSelectionIn,
    StructuralQuestionResponse,
)

router = APIRouter()


@router.post("/api/sheets/resolve")
def resolve_sheets(
    body: SheetResolveRequest,
    store=Depends(get_profile_store),
    schema_store=Depends(get_schema_store),
    client=Depends(get_anthropic_client),
    # D-10-13: a gate only, not a value this route reads -- the dependency's
    # sole job is to raise 401 for a signed-out request.
    user: User = Depends(require_user),
):
    entry = registry.pop(body.upload_token)
    if entry is None or entry.sheet_manifest is None or entry.tmp_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"no pending sheet question for token '{body.upload_token}'",
        )

    # EVERY selection is validated against the SERVER-RETAINED manifest and the
    # Schema store BEFORE a single byte is copied (T-11-22). A client-supplied
    # `sheet_name` reaching `parse()` raises `ValueError` for an unknown sheet,
    # which the generic catch below would report as a 500 -- a client input error
    # dressed as a server error. Validate first, fail closed, name the
    # consequence, and leave the filesystem untouched.
    try:
        schemas = _validated_selections(body.selections, entry, schema_store)
    except HTTPException:
        _unlink(entry.tmp_path)
        raise

    group = UploadGroup(members={}, source_file_name=entry.source_file_name)
    group_id = groups.put(group)

    members: list[SheetMemberOut] = []
    for selection in _in_manifest_order(body.selections, entry):
        member = _resolve_one_sheet(
            selection, schemas[selection.schema_name], entry, group_id,
            store=store, client=client,
        )
        group.members[selection.sheet_name] = member.response["upload_token"]
        members.append(member)

    # Every member now owns its own copy (or has already released it), so the
    # ORIGINAL retained workbook has no remaining reader and its bytes leave disk.
    _unlink(entry.tmp_path)
    return SheetGroupResponse(
        group_id=group_id, source_name=entry.source_file_name, members=members
    )


def _validated_selections(
    selections: list[SheetSelectionIn], entry: UploadEntry, schema_store
) -> dict[str, Schema]:
    """Refuse the whole request unless EVERY selection names a sheet the server
    itself offered and a Schema the store actually holds.

    All-or-nothing, deliberately: a partially-honoured resolve would ingest some
    sheets and silently swallow the rest, which is the very "discard without a
    word" behaviour this phase exists to kill.

    `SchemaStore.get_schema` is the ONLY route to a Schema here (D-11-23) -- the
    tombstone filter is structural, one layer down, so a deleted field or alias
    can never resurrect through a second read path opened here."""
    if not selections:
        raise HTTPException(
            status_code=422,
            detail=(
                "Nothing was ingested: no sheet was selected. Tick at least one "
                "sheet to ingest, or start again with a different file."
            ),
        )

    known = {sheet.name for sheet in entry.sheet_manifest or ()}
    schemas: dict[str, Schema] = {}
    for selection in selections:
        if selection.sheet_name not in known:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Nothing was ingested: this workbook has no sheet named "
                    f"'{selection.sheet_name}'."
                ),
            )
        if selection.schema_name not in schemas:
            schema = schema_store.get_schema(selection.schema_name)
            if schema is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No Schema named {selection.schema_name!r} exists.",
                )
            schemas[selection.schema_name] = schema
    return schemas


def _in_manifest_order(
    selections: list[SheetSelectionIn], entry: UploadEntry
) -> list[SheetSelectionIn]:
    """The members come back in WORKBOOK order, not in whatever order the client
    happened to serialize its checkboxes -- so the Review tabs read like the
    workbook the curator is looking at."""
    order = {sheet.name: index for index, sheet in enumerate(entry.sheet_manifest or ())}
    return sorted(selections, key=lambda selection: order[selection.sheet_name])


def _resolve_one_sheet(
    selection: SheetSelectionIn,
    schema: Schema,
    entry: UploadEntry,
    group_id: str,
    *,
    store,
    client,
) -> SheetMemberOut:
    """Parse ONE selected sheet and retain it as an ordinary upload.

    The branch choreography is `/api/upload`'s own, deliberately and exactly:
    structural question -> date question -> mapping. Re-deriving it here with any
    difference would be a second answer to a question the upload route already
    answers -- and omitting the `date_question` check is precisely the Confirm
    dead-end that bug 260712-qgc fixed once and plan 11-06 had to fix again.
    """
    field_set = service.field_set_from_schema(schema)
    member_path = _own_copy_of(entry.tmp_path)

    try:
        result = service.resolve_or_map(
            member_path, field_set,
            store=store, sheet=selection.sheet_name, strictness=entry.strictness,
            headers_only=entry.headers_only, client=client, schema=schema,
        )
    except service.MissingCredentialsError as exc:
        _unlink(member_path)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except anthropic.AuthenticationError as exc:
        _unlink(member_path)
        raise HTTPException(
            status_code=401, detail="Anthropic rejected the credentials."
        ) from exc
    except (anthropic.APIError, ValueError) as exc:
        _unlink(member_path)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if isinstance(result, StructureQuestion):
        # SHEET-04: this sheet failed a gate and the human selected it anyway --
        # so it raises its OWN question, here, in its OWN member. It is never
        # dropped. The member keeps ITS temp copy (nobody else's) alive for
        # `/api/structural-hint/resolve`, which re-parses `entry.sheet` (11-06)
        # rather than re-ranking the workbook and silently answering about a
        # different sheet.
        token = registry.put(
            _member_entry(
                entry, schema, selection, group_id, field_set,
                tmp_path=member_path,
            )
        )
        return _member(selection, StructuralQuestionResponse.from_question(result, token))

    if result.date_question.has_conflicts:
        token = registry.put(
            _member_entry(
                entry, schema, selection, group_id, field_set,
                tmp_path=None, table=result.table, provenance=result.provenance,
                proposal=result.proposal, escalation=result.escalation,
            )
        )
        _unlink(member_path)
        return _member(
            selection,
            DateFormatQuestionResponse.from_question(
                result.date_question, token, headers_only=entry.headers_only
            ),
        )

    token = registry.put(
        _member_entry(
            entry, schema, selection, group_id, field_set,
            tmp_path=None, table=result.table, provenance=result.provenance,
        )
    )
    _unlink(member_path)
    vendor_memory = service.recall_vendor(result.table, field_set, schema, store)
    return _member(
        selection,
        MappingResponse.from_proposal(
            result.proposal, result.provenance, token,
            escalation=result.escalation, vendor_memory=vendor_memory,
            source_name=entry.source_file_name,
        ),
    )


def _member_entry(
    entry: UploadEntry,
    schema: Schema,
    selection: SheetSelectionIn,
    group_id: str,
    field_set,
    **shape,
) -> UploadEntry:
    """One member's `UploadEntry` -- an ORDINARY one (D-11-20).

    `group_id` and `sheet` are what make it a member, and they ride on the ENTRY
    rather than only in the group's token map for a reason: a member that goes on
    to answer a structural or date question is re-put under a FRESH token, so the
    group's original map goes stale while the entry's own membership survives the
    hop.

    `schema_name`/`sheet`/`strictness` are the resolution context every resolve
    route needs to re-run the IDENTICAL resolution this one just ran (11-06,
    D-11-22) -- the crosswalk pre-fill, the escalation line, the vendor pre-fill
    that `/api/confirm` then requires, and the exact worksheet the human chose."""
    return UploadEntry(
        field_set=field_set,
        headers_only=entry.headers_only,
        schema_name=schema.name,
        sheet=selection.sheet_name,
        strictness=entry.strictness,
        source_file_name=entry.source_file_name,
        group_id=group_id,
        **shape,
    )


def _member(selection: SheetSelectionIn, response) -> SheetMemberOut:
    return SheetMemberOut(sheet_name=selection.sheet_name, response=response.model_dump())


def _own_copy_of(source: str) -> str:
    """This member's OWN copy of the workbook (T-11-24, Pitfall 3).

    Each member then owns its own lifecycle, so `structural_hint.py`'s unlinks
    and the registry's eviction-unlink stay correct with zero changes -- and one
    member's resolve can never delete another member's file out from under it."""
    with tempfile.NamedTemporaryFile(suffix=Path(source).suffix, delete=False) as tmp:
        member_path = tmp.name
    shutil.copyfile(source, member_path)
    return member_path


def _unlink(path: str) -> None:
    """Remove a temp file, tolerating one that is already gone -- a missing file
    at unlink time is not itself a bug worth surfacing; a file left behind is
    (mirrors `structural_hint.py::_unlink_ignoring_missing`)."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
