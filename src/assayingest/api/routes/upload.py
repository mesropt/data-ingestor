"""POST /api/upload -- Task 1's walking-skeleton wiring: materialize the
upload, call `service.resolve_or_map`, serialize the ready-mapping branch.

Task 2 (same file) adds: the structural-question branch, temp-file cleanup
on the happy path, the extension/size/path-traversal upload guards, and
typed-exception-to-HTTP-status mapping -- none of that exists yet here by
design, so Task 2's own RED tests genuinely fail against this version.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from ... import service
from ...fields.loader import from_dict
from ..deps import get_anthropic_client, get_field_set_store, get_profile_store
from ..state import UploadEntry, registry
from ..wire import MappingResponse

router = APIRouter()


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
    """A thin adapter over `service.resolve_or_map` -- not `async def`, the
    fresh-Claude branch's Anthropic call is blocking (RESEARCH.md Pattern
    2); FastAPI runs plain `def` in its own threadpool.
    """
    resolved_field_set = _resolve_field_set(field_set, field_set_template_id, field_set_store)
    suffix = Path(file.filename or "").suffix or ".csv"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    result = service.resolve_or_map(
        tmp_path, resolved_field_set,
        store=store, sheet=sheet, headers_only=headers_only, client=client,
    )

    token = registry.put(
        UploadEntry(
            field_set=resolved_field_set, headers_only=headers_only,
            tmp_path=None, table=result.table,
        )
    )
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
