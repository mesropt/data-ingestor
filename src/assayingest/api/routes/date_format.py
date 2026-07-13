"""POST /api/date-format/resolve (D-10-07, INGEST-04) -- apply the human's
per-column date order and return the SAME `kind="mapping"` `MappingResponse`
the original upload would have, with NO re-parse: the `RawTable` and the
resolved `MappingProposal` the file's date question was raised against are
already retained under `upload_token` (mirrors `structural_hint.py`/
`reconcile.py`'s "pop the retained entry, redo the domain-level step, re-put
under a fresh token" shape) -- but unlike either of those, this route never
touches the filesystem: on the date-question branch `tmp_path` is already
`None` (the data file left disk at parse time), so there is nothing left to
clean up and nothing to re-read.

Security-critical (T-10-21): the client sends an ORDER
(`day_first`/`month_first`), never a strptime format string --
`DateFormatChoiceIn` carries no `date_format` field at all, so there is
nothing for a tampered client to send that this route would read as a
format. The server re-classifies the retained column and derives the
concrete format for the chosen order itself, via the SAME
`service.resolve_date_formats` the original upload/resolve already ran
(mirroring `service.confirm`'s "rebuild fresh, never trust the client's
readiness claim" discipline).

Needs no `require_verified_user` gate: this route reads and re-validates a
retained upload, mutating no governed state -- the same posture
`/api/structural-hint/resolve` already has.

D-10-13/T-10-22 (supersedes the app-wide-sign-in-is-a-UI-level-gate note this
docstring previously carried): gated by `require_user` -- a signed-out
client must not be able to drive a retained, date-question-pending upload to
completion here either. This mirrors `structural_hint.py`'s own gate exactly,
so the two resolve routes stay consistent with each other and with
`/api/upload`.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException

from ... import service
from ...auth.models import User
from ...domain.models import MappingProposal
from ...parsing.structure.date_order import DateOrder
from ...validation.validator import validate
from ..deps import get_profile_store, get_schema_store, require_user
from ..state import UploadEntry, registry
from ..wire import DateFormatResolveRequest, MappingResponse

router = APIRouter()


@router.post("/api/date-format/resolve")
def resolve_date_format(
    body: DateFormatResolveRequest,
    store=Depends(get_profile_store),
    schema_store=Depends(get_schema_store),
    # D-10-13: a gate only, not a value this route reads -- the dependency's
    # sole job is to raise 401 for a signed-out request.
    user: User = Depends(require_user),
):
    entry = registry.pop(body.upload_token)
    if entry is None or entry.table is None or entry.proposal is None:
        raise HTTPException(
            status_code=404,
            detail=f"no pending date question for token '{body.upload_token}'",
        )

    answers = {choice.target_field: DateOrder(choice.order) for choice in body.choices}

    try:
        resolution = service.resolve_date_formats(
            entry.table, entry.proposal, entry.field_set, answers=answers
        )
    except service.UnresolvedDateColumnsError as exc:
        # F2/P1-style fail-closed (T-10-22): nothing was assembled or
        # returned -- the client must answer EVERY ambiguous column, never
        # a partial or empty `choices` list.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # validate() is additive-only (Pattern 2/P1): it may only OR a violation
    # IN, never clear one back to False. `entry.proposal` is the retained
    # proposal from the ORIGINAL validate() pass, which ran BEFORE this
    # column's order was known -- so its date-typed fields still carry
    # whatever `needs_confirmation` that first pass set (True, for a
    # genuinely ambiguous column). Re-validating that proposal as-is would
    # permanently carry the stale flag forward even once the override
    # resolves it. Mirrors `service.confirm`'s "rebuild fresh, never trust a
    # stale readiness claim" discipline: reset every mapping's
    # needs_confirmation before re-validating, so this pass -- now armed
    # with the human's resolved date_formats -- decides fresh, from
    # scratch, exactly like the very first validate() call would have if it
    # had known the order all along.
    fresh_proposal = MappingProposal(
        source_columns=entry.proposal.source_columns,
        field_mappings=[replace(m, needs_confirmation=False) for m in entry.proposal.field_mappings],
    )
    proposal = validate(
        entry.table, fresh_proposal, entry.field_set, strictness=entry.strictness,
        date_formats=resolution.formats, date_contradictions=resolution.contradictions,
    )

    # Resolved to a mapping (P2): the retained table/field set are all the
    # rest of the flow needs -- there is no tmp_path to unlink (it was
    # already None when this entry was first retained), so nothing here
    # touches the filesystem at all, unlike structural_hint.py/reconcile.py.
    #
    # D-10-08: retain the ANSWER (an order, never a format) onto the fresh
    # entry -- the one thing `/api/confirm` cannot re-derive on its own. It
    # already crossed `DateFormatChoiceIn`'s `Literal["day_first",
    # "month_first"]` boundary above, so nothing further needs re-checking
    # here.
    token = registry.put(
        UploadEntry(
            field_set=entry.field_set, headers_only=entry.headers_only,
            tmp_path=None, table=entry.table, provenance=entry.provenance,
            date_answers=answers, source_file_name=entry.source_file_name,
            # 11-08 (the 11-07 handoff): group membership survives the answer.
            # Without these two fields the members that needed a date question
            # -- the ones most likely to matter -- would arrive at Confirm with
            # `group_id is None` and silently vanish from "Download All".
            sheet=entry.sheet, group_id=entry.group_id,
        )
    )
    # 10-09/INGEST-02: thread the same remembered-vendor lookup the plain
    # upload path runs -- otherwise a file needing a date question would
    # silently lose the pre-fill a clean file gets, an arbitrary
    # inconsistency. `entry.schema_name` is the governed Schema (if any) the
    # original upload targeted; re-fetched here since UploadEntry retains
    # only the name, never the Schema object itself.
    schema = schema_store.get_schema(entry.schema_name) if entry.schema_name else None
    vendor_memory = service.recall_vendor(entry.table, entry.field_set, schema, store)
    return MappingResponse.from_proposal(
        proposal, entry.provenance, token,
        escalation=entry.escalation, vendor_memory=vendor_memory,
        source_name=entry.source_file_name,
    )
