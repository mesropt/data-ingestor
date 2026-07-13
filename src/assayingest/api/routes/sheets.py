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
from dataclasses import replace
from pathlib import Path

import anthropic
from fastapi import APIRouter, Depends, HTTPException

from ... import service
from ...auth.models import User
from ...domain.models import Schema
from ...parsing.hint import StructuralHint, StructureQuestion
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
    # GET, not POP: the sheet question stays answerable after it has been
    # answered, so the curator can go BACK to it -- change a Schema, tick a table
    # they skipped -- without re-uploading the workbook. Every member already
    # takes its OWN copy of the file (`_own_copy_of`), so a retained original has
    # no reader to fight with, and the registry still owns its whole lifecycle:
    # eviction unlinks it exactly as before.
    entry = registry.get(body.upload_token)
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
    # consequence, and leave the filesystem untouched. A rejected answer leaves
    # the question STANDING, workbook included: deleting it here would turn "you
    # picked a Schema that no longer exists" into "upload the file again", which
    # is the tool punishing a human for its own 422.
    schemas = _validated_selections(body.selections, entry, schema_store)

    group = UploadGroup(members={}, source_file_name=entry.source_file_name)
    group_id = groups.put(group)

    members: list[SheetMemberOut] = []
    for selection in _in_manifest_order(body.selections, entry):
        member = _resolve_one_sheet(
            selection, schemas[selection.schema_name], entry, group_id,
            store=store, client=client,
        )
        # Keyed by the MEMBER's name, not the sheet's: four tables of one sheet
        # are four members, and a sheet-keyed dict would keep only the last.
        group.members[member.sheet_name] = member.response["upload_token"]
        members.append(member)

    # The ORIGINAL is deliberately NOT unlinked: every member holds its own copy,
    # and the retained one is what a Back to the sheet question re-reads. The
    # registry unlinks it on eviction, as it always has -- it remains the single
    # owner of this file's lifetime.
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

    known = {_selection_key(sheet) for sheet in entry.sheet_manifest or ()}
    schemas: dict[str, Schema] = {}
    for selection in selections:
        if _selection_key(selection) not in known:
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


def _selection_key(item) -> tuple[str, int | None]:
    """What identifies ONE dataset in a workbook: the sheet, and -- when the sheet
    stacks several tables -- which table.

    A manifest entry and a client selection are keyed the same way, deliberately:
    the sheet name alone stopped being an identity the moment one sheet could
    yield four datasets, and a tick that could not tell `Lab Results` rows 11-17
    from rows 21-27 would map one table's numbers under another's columns."""
    return (item.sheet_name if hasattr(item, "sheet_name") else item.name, item.table_index)


def _entry_for(selection: SheetSelectionIn, entry: UploadEntry):
    """The server-retained manifest row this selection names -- the ONLY source of
    the layout that will be read (T-12-17: never the client's word for it)."""
    key = _selection_key(selection)
    return next(
        (row for row in entry.sheet_manifest or () if _selection_key(row) == key), None
    )


def _member_name(selection: SheetSelectionIn, entry: UploadEntry) -> str:
    """What to call this member on its Review tab.

    The table's OWN heading leads -- `Lab Results — Renal Function` -- because
    that is what the curator calls it and what they will search the sheet for.
    The row range is the fallback for a table the vendor left unnamed, and the
    tie-breaker if two panels somehow carry the same heading: two datasets that
    read identically on a tab strip are two chances to confirm the wrong one."""
    row = _entry_for(selection, entry)
    if row is None or row.table_index is None:
        return selection.sheet_name
    titles = [
        other.table_title
        for other in entry.sheet_manifest or ()
        if other.name == row.name and other.table_index is not None
    ]
    if row.table_title and titles.count(row.table_title) == 1:
        return f"{selection.sheet_name} — {row.table_title}"
    if row.table_title:
        return f"{selection.sheet_name} — {row.table_title} ({row.table_label})"
    return f"{selection.sheet_name} — {row.table_label}"


def _in_manifest_order(
    selections: list[SheetSelectionIn], entry: UploadEntry
) -> list[SheetSelectionIn]:
    """The members come back in WORKBOOK order, not in whatever order the client
    happened to serialize its checkboxes -- so the Review tabs read like the
    workbook the curator is looking at."""
    order = {
        _selection_key(sheet): index
        for index, sheet in enumerate(entry.sheet_manifest or ())
    }
    return sorted(selections, key=lambda selection: order[_selection_key(selection)])


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
    member_name = _member_name(selection, entry)
    member_path = _own_copy_of(entry.tmp_path)

    # The retained verdict for THIS sheet (12-05): the judge ran ONCE at upload
    # (D-12-14) and its verdict rides the server-retained manifest to resolve
    # time -- resolving ticked sheets costs ZERO extra Claude calls (D-12-02).
    # UNKNOWN ATTACHES: even a layout_unknown verdict rides the hint rather
    # than degrading to None. Post-Wave-C a None and an UNKNOWN both end at
    # the same question, but only the attached verdict can tell the human WHY
    # they are being asked -- a None that silently means "ask" is the
    # write-only dead end this phase exists to kill.
    manifest_row = _entry_for(selection, entry)
    retained_layout = manifest_row.layout if manifest_row is not None else None

    # A TABLE of a multi-table sheet is confirmed by being TICKED. The sheet
    # screen showed this table's header row and its row range, and the human
    # picked it out of the four on that sheet -- there is no layout question left
    # to ask, and re-asking one per table would make the answer they just gave
    # look like it had not been heard. An ordinary sheet still goes through
    # D-12-15's null hypothesis, unchanged.
    layout_confirmed = manifest_row is not None and manifest_row.table_index is not None

    if selection.ask_layout:
        # The disagree path (12-UI-SPEC Discretion 2): this member does NOT
        # apply the retained verdict. It gets the layout question -- proposal
        # = Claude's read, so the panel can render it -- inside its own Review
        # tab, and the ONE answer surface (StructuralHintPanel) resolves it
        # from there. Never a second inline editor.
        try:
            question = service.layout_question_for(
                member_path,
                selection.sheet_name,
                retained_layout,
                source_name=entry.source_file_name,
            )
        except Exception as exc:
            _unlink(member_path)
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        token = registry.put(
            _member_entry(
                entry, schema, selection, group_id, field_set,
                tmp_path=member_path,
            )
        )
        return _member(member_name, schema.name, StructuralQuestionResponse.from_question(question, token))

    try:
        result = service.resolve_or_map(
            member_path, field_set,
            store=store, sheet=selection.sheet_name, strictness=entry.strictness,
            headers_only=entry.headers_only, client=client, schema=schema,
            hint=StructuralHint(layout=retained_layout),
            # For an ordinary sheet the manifest's verdict is Claude's PROPOSAL,
            # never a human's answer -- resolve_or_map applies D-12-15's rule to
            # it: a confident row_per_record proceeds silently, everything else
            # returns the answerable layout question for this member. A ticked
            # TABLE is already the human's answer (see above).
            layout_confirmed=layout_confirmed,
            source_name=entry.source_file_name,
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
        return _member(member_name, schema.name, StructuralQuestionResponse.from_question(result, token))

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

    # WHICH TABLE these rows came from, stamped on the rows themselves. Every
    # table of a stacked sheet is the same worksheet, so the row provenance said
    # `Lab Results` for all four datasets and the export could not tell
    # Electrolytes from Proteins. `origin_sheet` is what the writers put in the
    # reserved `__source_sheet` column and what the manifest reads back, so
    # naming the table HERE fixes the data files and the audit trail together --
    # they cannot disagree, because they read the one value.
    table = result.table
    if manifest_row is not None and manifest_row.table_index is not None:
        table = replace(table, origin_sheet=member_name)

    token = registry.put(
        _member_entry(
            entry, schema, selection, group_id, field_set,
            tmp_path=None, table=table, provenance=result.provenance,
            source_table=member_name if manifest_row and manifest_row.table_index is not None else None,
        )
    )
    _unlink(member_path)
    vendor_memory = service.recall_vendor(result.table, field_set, schema, store)
    return _member(
        member_name,
        schema.name,
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


def _member(name: str, schema_name: str, response) -> SheetMemberOut:
    """One resolved dataset. `name` is what the curator sees on its Review tab --
    the sheet, plus its row range when the sheet held more than one table."""
    return SheetMemberOut(
        sheet_name=name, schema_name=schema_name, response=response.model_dump()
    )


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
