"""The field-set template repository seam (D-03) -- mirrors
`learning/store.py::ProfileStore` exactly: the interface a Postgres-backed
store (Phase 4+, multi-user API) will implement identically. The browser's
field-definition UI (UI-01) depends only on this abstract interface, never on
a driver directly (CLAUDE.md: "Map infrastructure models to domain models at
the layer boundary -- don't mix layers in one dataclass").
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..fields.models import FieldSet


class FieldSetTemplateStore(ABC):
    """The seam a Postgres-backed store (Phase 4+) implements identically.

    `PostgresFieldSetStore` (`postgres_field_set_store.py`) -- the same database
    `PostgresProfileStore` already uses (D-03) -- is the implementation, but
    nothing in the API layer may depend on that fact -- only on the three
    methods declared here. No more methods than the UI actually calls
    (list templates, save one, load one by id).
    """

    @abstractmethod
    def save(self, name: str, field_set: FieldSet) -> str:
        """Persist `field_set` under `name`, upserting on an identical
        `name` (a saved template name is a stable handle the UI lists by).
        Returns the template's id."""

    @abstractmethod
    def get(self, template_id: str) -> FieldSet | None:
        """The one field set matching this exact id, or `None` on any miss."""

    @abstractmethod
    def list(self) -> list[tuple[str, str]]:
        """Every saved template as `(id, name)` -- the UI's template picker."""
