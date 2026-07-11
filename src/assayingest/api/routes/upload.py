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
from pathlib import Path

import anthropic
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from ... import service
from ...fields.loader import from_dict
from ...parsing.hint import StructureQuestion
from ..deps import get_anthropic_client, get_field_set_store, get_profile_store
from ..state import UploadEntry, registry
from ..wire import MappingResponse, StructuralQuestionResponse

router = APIRouter()

#: T-04-04: `parsing/table.py` only ever accepts `.csv`/`.xlsx`, and names
#: `.xls` explicitly (with an actionable message) as an unsupported legacy
#: format -- the upload allowlist matches that exact set so a genuinely
#: unsupported extension is rejected here, before any bytes reach `parse()`,
#: rather than surfacing as a 500 from deep inside the parser.
_ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

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
    store=Depends(get_profile_store),
    field_set_store=Depends(get_field_set_store),
    client=Depends(get_anthropic_client),
):
    resolved_field_set = _resolve_field_set(field_set, field_set_template_id, field_set_store)
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

    try:
        result = service.resolve_or_map(
            tmp_path, resolved_field_set,
            store=store, sheet=sheet, headers_only=headers_only, client=client,
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
    return MappingResponse.from_proposal(result.proposal, result.provenance, token)


def _resolve_field_set(
    field_set_json: str | None, field_set_template_id: str | None, field_set_store
):
    """Build the `FieldSet` to map against, from either an inline JSON body
    (`field_set`) or a saved template id (`field_set_template_id`, D-03 --
    not yet backed by a real store until Plan 03)."""
    if field_set_json is not None:
        try:
            raw = json.loads(field_set_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=422, detail=f"field_set is not valid JSON: {exc}"
            ) from exc
        try:
            return from_dict(raw)
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
        return resolved
    raise HTTPException(
        status_code=422,
        detail="no field set provided: pass field_set (JSON) or field_set_template_id",
    )


def _validated_extension(filename: str | None) -> str:
    """T-04-04: only the extension is EVER derived from the client-supplied
    filename -- the actual temp path is always `tempfile`-generated below,
    never a path built from `filename` itself. This makes a traversal
    filename like `../../etc/passwd.csv` structurally inert: at most its
    extension is read."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot ingest: expected a .csv, .xlsx, or .xls file, got "
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
