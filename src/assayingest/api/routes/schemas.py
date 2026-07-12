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
from ..wire import PromoteRequest, SchemaAliasIn, SchemaFieldIn, SchemaOut

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
        # D-10-08/INGEST-05: the ONE call site that opts out of the
        # empty-fields guard -- an empty Schema is a legitimate starting
        # state (create, then populate via add_schema_field), unlike a
        # field-set upload, where an empty file is broken input.
        field_set = from_dict(body.field_set, allow_empty=True)
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


# D-07-04: this route stays AUGMENT-ONLY -- a machine may only ADD. Removals
# and rewrites go through the explicit edit routes below, NEVER through this
# one (D-10-12). `test_the_master_map_import_route_is_still_augment_only`
# fails loudly if this route is ever widened into an edit path.
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


# --- Phase 10: the explicit governed-Schema edit surface (D-10-12) -----------
#
# Five routes, each a thin adapter: deserialize -> service -> map typed error
# or result to HTTP, exactly like every route above. `require_verified_user`
# resolves BEFORE any route body runs (401 signed-out / 403 unverified,
# T-10-15) -- unconditionally, unlike `upload._reconcile_upload`'s conditional
# gate. The provenance actor for an added alias, and the `removed_by` on every
# tombstone, is ALWAYS `user.email` (T-10-16) -- never a client body field;
# neither `SchemaFieldIn` nor `SchemaAliasIn` carries one. Every one of these
# returns the fresh, authoritative `SchemaOut.from_schema(...)` so the
# frontend re-renders from server state rather than patching its own copy.


@router.post("/api/schemas/{name}/fields")
def add_schema_field(
    name: str,
    body: SchemaFieldIn,
    store=Depends(get_schema_store),
    user: User = Depends(require_verified_user),
) -> SchemaOut:
    try:
        updated = service.add_schema_field(store, name, body.field)
    except service.SchemaNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SchemaOut.from_schema(updated)


@router.patch("/api/schemas/{name}/fields/{field_name}")
def update_schema_field(
    name: str,
    field_name: str,
    body: SchemaFieldIn,
    store=Depends(get_schema_store),
    user: User = Depends(require_verified_user),
) -> SchemaOut:
    try:
        updated = service.update_schema_field(store, name, field_name, body.field)
    except service.SchemaNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.SchemaFieldNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SchemaOut.from_schema(updated)


@router.delete("/api/schemas/{name}/fields/{field_name}")
def remove_schema_field(
    name: str,
    field_name: str,
    store=Depends(get_schema_store),
    user: User = Depends(require_verified_user),
) -> SchemaOut:
    try:
        updated = service.remove_schema_field(store, name, field_name, removed_by=user.email)
    except service.SchemaNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.SchemaFieldNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SchemaOut.from_schema(updated)


@router.post("/api/schemas/{name}/fields/{field_name}/aliases")
def add_schema_alias(
    name: str,
    field_name: str,
    body: SchemaAliasIn,
    store=Depends(get_schema_store),
    user: User = Depends(require_verified_user),
) -> SchemaOut:
    try:
        updated = service.add_schema_alias(
            store, name, field_name, body.vendor, body.source_column, actor=user.email
        )
    except service.SchemaNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.SchemaFieldNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SchemaOut.from_schema(updated)


@router.delete("/api/schemas/{name}/fields/{field_name}/aliases")
def remove_schema_alias(
    name: str,
    field_name: str,
    vendor: str,
    source_column: str,
    store=Depends(get_schema_store),
    user: User = Depends(require_verified_user),
) -> SchemaOut:
    try:
        updated = service.remove_schema_alias(
            store, name, field_name, vendor, source_column, removed_by=user.email
        )
    except service.SchemaNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.SchemaFieldNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SchemaOut.from_schema(updated)
