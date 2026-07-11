"""GET/POST /api/schemas, GET/POST /api/schemas/{name}/master-map -- the
governed-Schema HTTP surface (D-07-03/04, SCHEMA-01/02/03).

Thin transport, no business logic: deserialize -> `service.promote` /
`service.export_master_map` / `service.import_master_map` -> map result or
typed error to HTTP, exactly as `field_sets.py`/`confirm.py` map their own
`ValueError`s. The domain `FieldSet` is built via `fields.loader.from_dict`
(the same `_validated_name` guard the CLI `--fields` flag enforces, T-07-08),
never a second weaker HTTP-layer check.

Both MUTATION routes (create, import) depend on `require_verified_user`: the
P1 governance gate is on the ENDPOINT, not the UI (T-07-05) -- a signed-out
request is 401 and a signed-in-but-unverified one is 403, before any store
work. The provenance actor (a Schema's `created_by`, an imported alias's
actor) is the server-resolved `user.email` or the map file's declared source
name, NEVER a client body field (T-07-06). Import is augment-only: it adds
missing fields/aliases and never discards or overwrites existing ones
(SCHEMA-03, the augment semantics live in `service.import_master_map`).
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from ... import service
from ...auth.models import User
from ...fields.loader import from_dict
from ..deps import get_schema_store, require_verified_user
from ..wire import PromoteRequest, SchemaOut

router = APIRouter()


@router.post("/api/schemas")
def create_schema(
    body: PromoteRequest,
    store=Depends(get_schema_store),
    user: User = Depends(require_verified_user),
) -> SchemaOut:
    # The auth gate (require_verified_user) resolves BEFORE this body runs --
    # a signed-out (401) / unverified (403) request never reaches the store.
    # The actor is taken from the server-resolved `user`, never `body`
    # (T-07-06); `PromoteRequest` has no `created_by` field to trust.
    try:
        field_set = from_dict(body.field_set)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    schema = service.promote(
        field_set, created_by=user.email, store=store, name=body.name
    )
    return SchemaOut.from_schema(schema)


@router.get("/api/schemas")
def list_schemas(store=Depends(get_schema_store)) -> list[SchemaOut]:
    return [SchemaOut.from_schema(schema) for schema in store.list_schemas()]


@router.get("/api/schemas/{name}/master-map")
def export_master_map(name: str, store=Depends(get_schema_store)) -> dict:
    schema = store.get_schema(name)
    if schema is None:
        raise HTTPException(status_code=404, detail=f"no schema '{name}'")
    return service.export_master_map(schema)


@router.post("/api/schemas/{name}/master-map")
def import_master_map(
    name: str,
    envelope: dict = Body(...),
    store=Depends(get_schema_store),
    user: User = Depends(require_verified_user),
) -> SchemaOut:
    # Gate resolves first (401/403) before any store work. The provenance
    # actor for imported aliases is the map file's DECLARED source name
    # (`envelope["name"]`), falling back to the target path name -- never a
    # client-trusted actor field (T-07-06). Augment-only (SCHEMA-03) lives in
    # the service; the route only maps typed errors to HTTP.
    source_name = envelope.get("name") or name
    try:
        updated = service.import_master_map(
            store, name, envelope, source_name=source_name
        )
    except service.SchemaNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, KeyError) as exc:
        # A malformed envelope (missing key, invalid field name via the shared
        # loader guard, T-07-08) is a 422, never a 500.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SchemaOut.from_schema(updated)
