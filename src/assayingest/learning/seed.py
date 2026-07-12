"""Seed the shipped starter presets into a `FieldSetTemplateStore` at
startup (FIELD-05, quick 260712-e0e).

Insert-if-absent, never upsert (T-e0e-02): `SqliteFieldSetStore.save`
upserts on `UNIQUE(name)` and mints a fresh uuid4 id on every call, so
calling it unconditionally on every restart would both duplicate nothing
(good) and silently re-mint every preset's id (bad) -- breaking the
frontend's persisted last-used template id, and reverting any curator edit
made under a preset's name. Reading `store.list()` once and skipping
already-present names is what keeps seeding both idempotent and id-stable.

`learning` already imports `fields` elsewhere (`sqlite_field_set_store.py`
imports `fields.loader`/`fields.models`); this keeps that same dependency
direction rather than making `fields` depend on `learning`.
"""

from __future__ import annotations

from ..fields.presets import load_presets
from .field_set_store import FieldSetTemplateStore


def seed_presets(store: FieldSetTemplateStore) -> list[str]:
    """Insert every shipped preset not already present in `store` by name.

    Returns the names actually seeded (empty on a store that already holds
    all of them, or a repeat call) -- callers that want to log/report what
    happened don't need a second `store.list()` diff.
    """
    existing_names = {name for _, name in store.list()}
    seeded: list[str] = []
    for name, field_set in load_presets():
        if name in existing_names:
            continue
        store.save(name, field_set)
        seeded.append(name)
    return seeded
