"""POST /api/upload -- a thin adapter over `service.resolve_or_map`
(API-01/03, UI-02, RESEARCH.md Pattern 1): materialize the upload to a temp
path, call the seam, serialize whichever branch it returns, and clean up
(P2). Not `async def` -- the fresh-Claude branch's Anthropic call is
blocking (RESEARCH.md Pattern 2); FastAPI runs plain `def` in its own
threadpool, so the event loop is never blocked.

Upload guards (T-04-04/T-04-05/T-04-06): only the extension is ever derived
from the client-supplied filename -- the actual temp path is always
`tempfile`-generated, never a path built from `filename` itself. A bounded
read rejects an oversized upload before it is ever fully buffered to disk.
The happy (mapping-resolved) path unlinks its temp file immediately; the
structural-question branch retains it, keyed by `upload_token`, until a
future `/api/structural-hint/resolve` (Plan 03) re-parses it.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import anthropic
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ... import service
from ...auth.models import User
from ...domain.models import ReconcileQuestion, Schema
from ...fields.loader import from_dict
from ...fields.models import FieldSet
from ...parsing.hint import StructureQuestion
from ...parsing.structure.grid import list_worksheets
from ..deps import (
    get_anthropic_client,
    get_field_set_store,
    get_profile_store,
    get_schema_store,
    require_user,
)
from ..state import UploadEntry, registry
from ..wire import (
    DateFormatQuestionResponse,
    MappingResponse,
    ReconcileQuestionResponse,
    SheetQuestionResponse,
    StructuralQuestionResponse,
)

router = APIRouter()

#: T-04-04/WR-02: `parsing/table.py` only ever accepts `.csv`/`.xlsx`, and
#: names `.xls` explicitly (with an actionable message) as an unsupported
#: legacy format -- the upload allowlist matches that exact set so a
#: genuinely unsupported extension is rejected here, before any bytes reach
#: `parse()`, rather than surfacing as a 500 from deep inside the parser.
#: `.xls` was previously (wrongly) included here, passing the allowlist
#: only to hit `parse()`'s own `ValueError` and surface as a 500 -- a
#: client input error reported as a server error (WR-02). It is handled as
#: its own case in `_validated_extension` instead, with the same actionable
#: "re-save as .xlsx" message `parsing/table.py` gives the CLI.
_ALLOWED_EXTENSIONS = {".csv", ".xlsx"}

#: Mirrors `parsing/table.py::_LEGACY_EXCEL_SUFFIXES` -- rejected with its
#: own actionable message rather than the generic "unsupported extension"
#: one (WR-02).
_LEGACY_EXCEL_SUFFIXES = {".xls"}

#: T-04-05: a reasonable ceiling for a synthetic-lab-file demo
#: (RESEARCH.md Assumption A2) -- no requirement mandates an exact number,
#: but SOME explicit bound must exist rather than none.
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
_CHUNK_SIZE = 1024 * 1024


class _UploadTooLargeError(Exception):
    """Raised internally when a bounded read exceeds `_MAX_UPLOAD_BYTES` --
    caught by the route and translated to HTTP 413."""


@router.post("/api/upload")
def upload(
    file: UploadFile,
    field_set: str | None = Form(None),
    field_set_template_id: str | None = Form(None),
    headers_only: bool = Form(False),
    sheet: str | None = Form(None),
    map_file: UploadFile | None = File(None),
    schema_name: str | None = Form(None),
    vendor: str | None = Form(None),
    store=Depends(get_profile_store),
    field_set_store=Depends(get_field_set_store),
    schema_store=Depends(get_schema_store),
    client=Depends(get_anthropic_client),
    user: User = Depends(require_user),
):
    # D-11-16: `schema_name` is genuinely optional for a MULTI-SHEET workbook --
    # the sheet question resolves the Schema per sheet instead. But whether this
    # upload IS a multi-sheet workbook cannot be known until its bytes are on
    # disk, so the "no target at all" 422 is DEFERRED (`require_target=False`)
    # until that is settled. Every OTHER 422/404 this function raises (an
    # unknown Schema name, malformed field_set JSON, a missing template) keeps
    # its exact position and its exact status -- only the one refusal that
    # D-11-16 makes conditional moves.
    resolved = _resolve_field_set(
        field_set, field_set_template_id, schema_name, field_set_store, schema_store,
        require_target=False,
    )

    # D-08-01/05: a map file switches the request onto the reconcile path (an
    # augment against a governed Schema), which is verified-user gated. A plain
    # upload (no map file) keeps the EXISTING open contract untouched. The
    # reconcile path always needs a target, so its 422 stays exactly where it
    # was -- before the extension check, byte for byte as today.
    if map_file is not None:
        if resolved is None:
            raise _no_target_error()
        suffix = _validated_extension(file.filename)
        return _reconcile_upload(
            file, suffix, resolved.field_set, schema_name, vendor, map_file,
            headers_only=headers_only, sheet=sheet, store=store,
            schema_store=schema_store, client=client, user=user,
        )

    suffix = _validated_extension(file.filename)

    try:
        tmp_path = _write_bounded_temp_file(file, suffix)
    except _UploadTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=(
                "Cannot ingest: file exceeds the "
                f"{_MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit."
            ),
        ) from exc

    # SHEET-01/D-11-16: the trigger is `>1 worksheet` AND no explicit `sheet=` --
    # REGARDLESS of whether a Schema was chosen. A Schema picked in the dropdown
    # is a DEFAULT PRE-SELECTION and never suppresses the question: the browser
    # always sends one, so gating on "no Schema" would have made this entire
    # feature unreachable from the UI.
    #
    # Today the tool guesses instead: `_resolve_sheet` ranks the worksheets,
    # takes the winner, and silently discards every other sheet (meridian's
    # LEGEND, right now). This branch is what kills that guess.
    # A file the parser cannot read at all -- an empty file, a corrupt workbook --
    # is a fact about the UPLOAD, not a server fault and not a mapping failure.
    # It is a 422 carrying the parser's OWN sentence ("the file is empty -- there
    # is no table to read"), because a 500 here reaches the browser as the
    # generic "Claude couldn't map this file" fallback, which is simply untrue:
    # Claude was never called. The tool must not blame the model for an empty
    # file.
    try:
        if _asks_which_sheets(tmp_path, suffix, sheet, schema_name):
            return _sheet_question(
                tmp_path, schema_name,
                headers_only=headers_only, source_file_name=file.filename,
                store=store, schema_store=schema_store, client=client,
            )

        # A CSV with no Schema gets the SAME screen, from a one-entry manifest
        # built on its own headers. A CSV has no worksheets, which was the only
        # reason it was excluded -- the Schema scorer needs headers, and a CSV
        # has those.
        if suffix == ".csv" and resolved is None:
            return _sheet_question(
                tmp_path, schema_name,
                headers_only=headers_only, source_file_name=file.filename,
                store=store, schema_store=schema_store, client=client,
                is_csv=True,
            )
    except (ValueError, FileNotFoundError) as exc:
        _unlink_quietly(tmp_path)
        raise HTTPException(
            status_code=422, detail=_named_for_the_curator(exc, tmp_path, file.filename)
        ) from exc

    # The single-sheet path (a CSV, a one-sheet workbook, or any upload with an
    # explicit `sheet=`) is untouched from here down -- including this 422, which
    # is the same refusal `_resolve_field_set` raised in place before D-11-16
    # made it conditional.
    if resolved is None:
        os.unlink(tmp_path)
        raise _no_target_error()
    resolved_field_set = resolved.field_set
    resolved_schema = resolved.schema

    try:
        result = service.resolve_or_map(
            tmp_path, resolved_field_set,
            store=store, sheet=sheet, headers_only=headers_only, client=client,
            schema=resolved_schema,
            source_name=file.filename,
        )
    except service.MissingCredentialsError as exc:
        os.unlink(tmp_path)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except anthropic.AuthenticationError as exc:
        os.unlink(tmp_path)
        raise HTTPException(
            status_code=401, detail="Anthropic rejected the credentials."
        ) from exc
    except (anthropic.APIError, ValueError) as exc:
        os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if isinstance(result, StructureQuestion):
        # P2/T-04-06: the file must survive until a future
        # /api/structural-hint/resolve (Plan 03) re-parses it with the
        # human's hint -- NOT cleaned up on this branch.
        #
        # 11-06/D-11-22: `schema_name` and `sheet` are retained alongside the
        # file, so the resolve route can re-run the SAME resolution the
        # direct path would have -- crosswalk prefill, escalation, vendor
        # pre-fill, and (T-11-21) the exact worksheet the human chose. The
        # entry's `strictness` keeps its default, the same "strict" this
        # route's own `resolve_or_map` call just ran under.
        token = registry.put(
            UploadEntry(
                field_set=resolved_field_set, headers_only=headers_only, tmp_path=tmp_path,
                schema_name=schema_name, sheet=sheet,
                source_file_name=file.filename,
            )
        )
        return StructuralQuestionResponse.from_question(result, token)

    if result.date_question.has_conflicts:
        # D-10-07: one or more mapped date columns are genuinely
        # order-ambiguous and no declared format covers them -- block the
        # mapping until the human answers once per column. Retain the
        # ALREADY-PARSED table + resolved proposal (tmp_path=None: nothing
        # is left to re-parse, mirroring the happy-path's own cleanup) so
        # /api/date-format/resolve needs no re-parse at all (T-08-08 applied
        # to a third question type).
        token = registry.put(
            UploadEntry(
                field_set=resolved_field_set, headers_only=headers_only,
                tmp_path=None, table=result.table, provenance=result.provenance,
                proposal=result.proposal, schema_name=schema_name,
                escalation=result.escalation, source_file_name=file.filename,
            )
        )
        os.unlink(tmp_path)
        return DateFormatQuestionResponse.from_question(
            result.date_question, token, headers_only=headers_only
        )

    # Happy path (P2): the parsed RawTable (headers+rows, already in
    # memory) is all the rest of the flow needs -- the original file's
    # bytes leave disk now.
    token = registry.put(
        UploadEntry(
            field_set=resolved_field_set, headers_only=headers_only,
            tmp_path=None, table=result.table, provenance=result.provenance,
            source_file_name=file.filename,
        )
    )
    os.unlink(tmp_path)
    # 10-09/INGEST-02: the remembered-vendor lookup -- profile match, then
    # crosswalk fallback, refusing to guess on ambiguity. `resolved_schema`
    # is None on the legacy field_set/CLI path, which recall_vendor degrades
    # to gracefully (never a misleading guess).
    vendor_memory = service.recall_vendor(result.table, resolved_field_set, resolved_schema, store)
    return MappingResponse.from_proposal(
        result.proposal, result.provenance, token,
        escalation=result.escalation, vendor_memory=vendor_memory,
        source_name=file.filename,
    )


def _asks_which_sheets(
    tmp_path: str, suffix: str, sheet: str | None, schema_name: str | None = None
) -> bool:
    """More than one real worksheet and no explicit `sheet=` (D-11-16's trigger)
    -- OR a workbook uploaded with no Schema at all, whatever its sheet count.

    The second arm is why the Upload page no longer demands a Schema up front.
    The sheet screen ALREADY proposes one per sheet, from the sheet's own
    headers -- so demanding the same answer before the file has even been read
    asked the human to guess at exactly what the tool is about to tell them.
    A one-sheet workbook goes to the same screen for the same reason: it has a
    sheet, and that sheet has a Schema proposal waiting for it.

    A CSV is deliberately NOT swept in: it has no worksheets, so there is no
    sheet screen to carry the proposal, and the 422 below stays its answer.

    `list_worksheets` is what makes "real" structural rather than a guess -- a
    chartsheet is excluded by construction (D-17), so a workbook of one data
    sheet plus a chart is a SINGLE-sheet workbook here, exactly as it is to
    `parse()`. Counting `wb.sheetnames` instead would ask the human to choose
    between a table and a picture.

    An explicit `sheet=` means the human has already answered this question --
    asking it again would be asking them to repeat themselves, and it is the one
    thing that keeps `/api/structural-hint/resolve`'s own re-parse (which always
    passes the retained sheet, 11-06) off this branch.
    """
    if suffix != ".xlsx" or sheet is not None:
        return False
    try:
        worksheets = len(list_worksheets(tmp_path))
        return worksheets > 1 or (worksheets == 1 and schema_name is None)
    except Exception:
        # An unreadable workbook is not a sheet question. Fall through to the
        # single-sheet path, where `parse()` reaches the SAME openpyxl failure
        # and reports it exactly as it does today -- rather than inventing a
        # second, differently-worded verdict on the same broken file here.
        os.unlink(tmp_path)
        raise


def _sheet_question(
    tmp_path: str,
    schema_name: str | None,
    *,
    headers_only: bool,
    source_file_name: str | None,
    store,
    schema_store,
    client,
    is_csv: bool = False,
) -> SheetQuestionResponse:
    """Describe every worksheet, score every governed Schema against each, and
    ASK (SHEET-01/05, D-11-06).

    The manifest is built ABOVE `parse()` (D-11-21): `parse()`, `_resolve_sheet`,
    `rank_sheets` and `SheetRanking` are not touched by this phase at all. Each
    sheet the human then selects is parsed with an explicit `sheet=`, which
    short-circuits ranking and runs that sheet's OWN full gate chain -- which is
    how SHEET-04 comes for free.

    `schema_store.list_schemas()` is the ONLY route to a Schema here (D-11-23):
    the tombstone filter is structural, at the store's ORM->domain boundary, so
    the scorer needs no filter of its own and must never acquire a second one.

    Retains a FOURTH shape on `UploadEntry`: the temp file (the resolve re-parses
    it, once per selected sheet) plus the manifest itself, which is what
    `/api/sheets/resolve` validates the human's untrusted `sheet_name`s against
    (T-11-22). `field_set` is `None` -- there is no ONE field set for a workbook
    whose sheets may each want a different Schema, and inventing one here would
    be the very guess this branch exists to refuse.
    """
    if is_csv:
        # A CSV's manifest needs no layout judge (there is one reading of a CSV)
        # and therefore no `headers_only` either: nothing is sent to Claude here
        # but the headers, which are not cell values (D-10-05).
        #
        # The entry MUST be named for the real file: `tmp_path` is the server's
        # temp copy, and naming the entry after it would put `tmph2sg9kcg.csv` on
        # the curator's screen. `basename` because the name is untrusted text
        # from the browser -- it is a LABEL here, never a path to open.
        manifest = service.describe_csv(
            tmp_path, schema_store.list_schemas(),
            source_name=os.path.basename(source_file_name) if source_file_name else None,
            store=store, client=client,
        )
    else:
        manifest = service.describe_workbook(
            tmp_path,
            schema_store.list_schemas(),
            store=store,
            client=client,
            # The curator's privacy toggle must reach the layout judge's evidence
            # rendering (D-12-04/D-12-11): with a real client and headers_only
            # unset here, real cell values would leave the server in private mode.
            headers_only=headers_only,
        )
    token = registry.put(
        UploadEntry(
            field_set=None, headers_only=headers_only, tmp_path=tmp_path,
            schema_name=schema_name, sheet_manifest=manifest,
            source_file_name=source_file_name,
        )
    )
    return SheetQuestionResponse.from_manifest(manifest, token, default_schema=schema_name)


def _named_for_the_curator(
    exc: Exception, tmp_path: str, source_file_name: str | None
) -> str:
    """The parser's own sentence, with the SERVER'S temp file name swapped back
    for the one the curator actually uploaded.

    The parser names the file it was handed, and on this path it was handed a
    temp copy -- so its otherwise-perfect message arrives as "Cannot ingest
    tmpxyi9babm.csv: the file is empty". The curator has never seen that name and
    cannot act on it. The substitution is exact, not a guess: the temp basename
    is a unique token this function generated the message about.
    """
    detail = str(exc)
    if not source_file_name:
        return detail
    return detail.replace(os.path.basename(tmp_path), os.path.basename(source_file_name))


def _unlink_quietly(tmp_path: str) -> None:
    """Delete the temp upload, tolerating its absence.

    `_asks_which_sheets` already unlinks before re-raising on an unreadable
    workbook, so the caller's own cleanup would otherwise hit a
    `FileNotFoundError` and turn a clean 422 ("the file is empty") into a 500.
    Cleaning up twice must never be worse than not cleaning up at all.
    """
    try:
        os.unlink(tmp_path)
    except FileNotFoundError:
        pass


def _no_target_error() -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=(
            "no target provided: pass schema_name (the governed Schema to map "
            "against), or, for backward compatibility, field_set (JSON) or "
            "field_set_template_id"
        ),
    )


def _reconcile_upload(
    file, suffix, resolved_field_set, schema_name, vendor, map_file,
    *, headers_only, sheet, store, schema_store, client, user,
):
    """The map-file branch of `/api/upload` (D-08-01/05): a PURE adapter over
    `service.reconcile_or_map` -- gate, deserialize, call the seam, serialize
    whichever of the three arms it returns (reconcile_question | mapping |
    structural_question), and clean up.

    The 401 (signed-out) case is now owned entirely by the route's own
    `require_user` dependency (D-10-13) -- it raises before this function is
    ever entered, so `user` here is always a real, signed-in `User`. This
    function owns only the STRONGER verified-user gate: augmenting the
    governed master crosswalk is a governed action, so a signed-in-but-
    unverified user still gets 403 here -- mirroring `require_verified_user`'s
    403 semantics inline (it must stay CONDITIONAL here, applying only on the
    map-file path, so it cannot be a dependency). The conflict logic/augment
    all live in `service` (08-01); this route never re-implements them."""
    if not user.is_verified:
        raise HTTPException(
            status_code=403,
            detail="Verify your email to reconcile against a governed Schema.",
        )
    if not schema_name or not vendor:
        raise HTTPException(
            status_code=422,
            detail="A map file needs both schema_name and vendor to reconcile against.",
        )

    envelope = _read_bounded_json_envelope(map_file)
    try:
        # F3: validate the map file's SHAPE at the boundary so a structurally
        # malformed (but valid-JSON) envelope is a 422 client error, not a 500
        # from the later `reconcile_or_map` call whose ValueError catch is the
        # normal-failure 500 path for genuine mapping errors.
        Schema.from_master_map(envelope)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Cannot reconcile: {exc}"
        ) from exc

    try:
        tmp_path = _write_bounded_temp_file(file, suffix)
    except _UploadTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=(
                "Cannot ingest: file exceeds the "
                f"{_MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit."
            ),
        ) from exc

    try:
        result = service.reconcile_or_map(
            tmp_path, resolved_field_set,
            schema_store=schema_store, target_schema_name=schema_name, vendor=vendor,
            envelope=envelope, store=store, sheet=sheet,
            headers_only=headers_only, client=client,
        )
    except service.SchemaNotFoundError as exc:
        os.unlink(tmp_path)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.MissingCredentialsError as exc:
        os.unlink(tmp_path)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except anthropic.AuthenticationError as exc:
        os.unlink(tmp_path)
        raise HTTPException(
            status_code=401, detail="Anthropic rejected the credentials."
        ) from exc
    except (anthropic.APIError, ValueError) as exc:
        os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if isinstance(result, ReconcileQuestion):
        # P1/D-08-02: the map file disagrees with the master -- augment/map
        # NOTHING and retain the DATA file + map envelope + schema/vendor under
        # the token, so /api/reconcile/resolve can re-augment + re-map once the
        # human picks a side (mirrors the StructureQuestion retention branch).
        token = registry.put(
            UploadEntry(
                field_set=resolved_field_set, headers_only=headers_only,
                tmp_path=tmp_path, map_envelope=envelope,
                target_schema_name=schema_name, vendor=vendor,
                source_file_name=file.filename,
            )
        )
        return ReconcileQuestionResponse.from_question(result, token, schema_name, vendor)

    if isinstance(result, StructureQuestion):
        # A structural ambiguity still takes precedence over reconcile -- retain
        # the file for /api/structural-hint/resolve exactly as the plain path does.
        token = registry.put(
            UploadEntry(
                field_set=resolved_field_set, headers_only=headers_only, tmp_path=tmp_path,
                source_file_name=file.filename,
            )
        )
        return StructuralQuestionResponse.from_question(result, token)

    # Reconciled straight to a mapping (P2): the crosswalk was augmented and the
    # parsed RawTable is all the rest of the flow needs -- the data file leaves
    # disk now, and the result lands in the SAME review UI as a plain mapping.
    token = registry.put(
        UploadEntry(
            field_set=resolved_field_set, headers_only=headers_only,
            tmp_path=None, table=result.table, provenance=result.provenance,
            source_file_name=file.filename,
        )
    )
    os.unlink(tmp_path)
    return MappingResponse.from_proposal(
        result.proposal, result.provenance, token, source_name=file.filename
    )


def _read_bounded_json_envelope(map_file: UploadFile) -> dict:
    """T-08-07: read the uploaded map file under the SAME `_MAX_UPLOAD_BYTES`
    ceiling as the data file (413 on overflow, never an unbounded `.read()`),
    then `json.loads` it into a master-map envelope. Invalid JSON is a client
    input error naming the consequence (422), not a 500 from deep in the
    service's `Schema.from_master_map` parse."""
    total = 0
    chunks: list[bytes] = []
    while True:
        chunk = map_file.file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Cannot ingest: map file exceeds the "
                    f"{_MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit."
                ),
            )
        chunks.append(chunk)
    try:
        return json.loads(b"".join(chunks))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot reconcile: the map file is not valid JSON: {exc}",
        ) from exc


@dataclass(frozen=True)
class _ResolvedTarget:
    """What `_resolve_field_set` resolves to: the `FieldSet` to map against,
    plus (D-10-02/03) the governed `Schema` it was derived from, when one was
    named -- `None` on the legacy `field_set`/`field_set_template_id`
    branches, which have no Schema at all. The route threads `schema` into
    `service.resolve_or_map`'s Python-first pre-fill; a small frozen
    dataclass keeps this a single lookup rather than two parallel ones."""

    field_set: FieldSet
    schema: Schema | None = None


def _resolve_field_set(
    field_set_json: str | None,
    field_set_template_id: str | None,
    schema_name: str | None,
    field_set_store,
    schema_store,
    *,
    require_target: bool = True,
) -> _ResolvedTarget | None:
    """Build the target to map against (D-10-02): a named governed `Schema`
    (`schema_name`, checked FIRST -- the browser's only path per the locked
    three-control Upload UI) wins over an inline JSON body (`field_set`,
    which the CLI and every pre-Phase-10 test still send) or a saved
    template id (`field_set_template_id`, D-03). `field_set`/
    `field_set_template_id` remain fully supported -- this is additive, not
    a replacement (10-05's own objective).

    `require_target=False` (D-11-16, the ONE branch this phase adds) returns
    `None` instead of raising when NO target was given at all -- because a
    multi-sheet workbook no longer needs one: its sheet question resolves the
    Schema per sheet, and a workbook whose sheets each want a different Schema
    has no single answer to give here anyway. The caller re-raises the identical
    422 the moment it learns the upload is NOT a multi-sheet workbook. Every
    other refusal below -- an unknown Schema name (404), malformed `field_set`
    JSON (422), an unavailable or unknown template (501/404) -- is unconditional
    and unchanged: a target that was SUPPLIED and is WRONG is always an error,
    whatever the file turns out to be."""
    if schema_name is not None:
        schema = schema_store.get_schema(schema_name)
        if schema is None:
            raise HTTPException(
                status_code=404, detail=f"No Schema named {schema_name!r} exists."
            )
        return _ResolvedTarget(field_set=service.field_set_from_schema(schema), schema=schema)
    if field_set_json is not None:
        try:
            raw = json.loads(field_set_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=422, detail=f"field_set is not valid JSON: {exc}"
            ) from exc
        try:
            return _ResolvedTarget(field_set=from_dict(raw))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if field_set_template_id is not None:
        if field_set_store is None:
            raise HTTPException(
                status_code=501,
                detail="field-set templates are not available yet.",
            )
        resolved = field_set_store.get(field_set_template_id)
        if resolved is None:
            raise HTTPException(
                status_code=404,
                detail=f"no field-set template '{field_set_template_id}'",
            )
        return _ResolvedTarget(field_set=resolved)
    if not require_target:
        return None
    raise _no_target_error()


def _validated_extension(filename: str | None) -> str:
    """T-04-04: only the extension is EVER derived from the client-supplied
    filename -- the actual temp path is always `tempfile`-generated below,
    never a path built from `filename` itself. This makes a traversal
    filename like `../../etc/passwd.csv` structurally inert: at most its
    extension is read."""
    suffix = Path(filename or "").suffix.lower()
    if suffix in _LEGACY_EXCEL_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot ingest: the old binary .xls format is not supported "
                "— open it in a spreadsheet and re-save as .xlsx."
            ),
        )
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot ingest: expected a .csv or .xlsx file, got "
                f"'{suffix or '(no extension)'}'"
            ),
        )
    return suffix


def _write_bounded_temp_file(file: UploadFile, suffix: str) -> str:
    """T-04-05: read in fixed-size chunks and abort (removing the partial
    file) the moment the running total exceeds `_MAX_UPLOAD_BYTES` -- an
    unbounded `.read()` would buffer an arbitrarily large upload into
    memory/disk before any check ever ran."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        total = 0
        while True:
            chunk = file.file.read(_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_UPLOAD_BYTES:
                tmp.close()
                os.unlink(tmp_path)
                raise _UploadTooLargeError()
            tmp.write(chunk)
    return tmp_path
