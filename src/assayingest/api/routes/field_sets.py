"""GET/POST /api/field-sets, GET /api/field-sets/{id} -- field-set template
CRUD (UI-01, D-03): a thin wrapper over `FieldSetTemplateStore` (Task 1).
No business logic here -- `fields.loader.from_dict` builds (and validates)
the domain `FieldSet` from the request body exactly as a file-loaded field
set is built, so a malicious/malformed field name gets the identical
`_validated_name` guard the CLI's `--fields` flag already enforces
(T-04-11), never a second, weaker HTTP-layer check.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...fields.loader import from_dict
from ..deps import get_field_set_store
from ..wire import FieldSetIn, FieldSetOut

router = APIRouter()


@router.get("/api/field-sets")
def list_field_sets(store=Depends(get_field_set_store)) -> list[FieldSetOut]:
    return [
        FieldSetOut(id=template_id, name=name, field_set=store.get(template_id).to_dict())
        for template_id, name in store.list()
    ]


@router.post("/api/field-sets")
def save_field_set(body: FieldSetIn, store=Depends(get_field_set_store)) -> dict:
    try:
        field_set = from_dict(body.field_set)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    template_id = store.save(body.name, field_set)
    return {"id": template_id}


@router.get("/api/field-sets/{template_id}")
def get_field_set(template_id: str, store=Depends(get_field_set_store)) -> dict:
    field_set = store.get(template_id)
    if field_set is None:
        raise HTTPException(
            status_code=404, detail=f"no field-set template '{template_id}'"
        )
    return field_set.to_dict()
