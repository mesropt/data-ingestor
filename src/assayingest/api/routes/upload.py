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
    resolved = _resolve_field_set(
        field_set, field_set_template_id, schema_name, field_set_store, schema_store
    )
    resolved_field_set = resolved.field_set
    resolved_schema = resolved.schema
    suffix = _validated_extension(file.filename)

    # D-08-01/05: a map file switches the request onto the reconcile path (an
    # augment against a governed Schema), which is verified-user gated. A plain
    # upload (no map file) keeps the EXISTING open contract untouched.
    if map_file is not None:
        return _reconcile_upload(
            file, suffix, resolved_field_set, schema_name, vendor, map_file,
            headers_only=headers_only, sheet=sheet, store=store,
            schema_store=schema_store, client=client, user=user,
        )

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
        result = service.resolve_or_map(
            tmp_path, resolved_field_set,
            store=store, sheet=sheet, headers_only=headers_only, client=client,
            schema=resolved_schema,
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
        token = registry.put(
            UploadEntry(
                field_set=resolved_field_set, headers_only=headers_only, tmp_path=tmp_path
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
                escalation=result.escalation,
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
        )
    )
    os.unlink(tmp_path)
    return MappingResponse.from_proposal(
        result.proposal, result.provenance, token, escalation=result.escalation
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
            )
        )
        return ReconcileQuestionResponse.from_question(result, token, schema_name, vendor)

    if isinstance(result, StructureQuestion):
        # A structural ambiguity still takes precedence over reconcile -- retain
        # the file for /api/structural-hint/resolve exactly as the plain path does.
        token = registry.put(
            UploadEntry(
                field_set=resolved_field_set, headers_only=headers_only, tmp_path=tmp_path
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
        )
    )
    os.unlink(tmp_path)
    return MappingResponse.from_proposal(result.proposal, result.provenance, token)


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
) -> _ResolvedTarget:
    """Build the target to map against (D-10-02): a named governed `Schema`
    (`schema_name`, checked FIRST -- the browser's only path per the locked
    three-control Upload UI) wins over an inline JSON body (`field_set`,
    which the CLI and every pre-Phase-10 test still send) or a saved
    template id (`field_set_template_id`, D-03). `field_set`/
    `field_set_template_id` remain fully supported -- this is additive, not
    a replacement (10-05's own objective)."""
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
    raise HTTPException(
        status_code=422,
        detail=(
            "no target provided: pass schema_name (the governed Schema to map "
            "against), or, for backward compatibility, field_set (JSON) or "
            "field_set_template_id"
        ),
    )


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
