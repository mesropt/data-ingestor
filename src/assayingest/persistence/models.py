"""The six ORM entities -- the ONLY place this project describes its tables.

Three column choices below look like they could be "modernized". Each one would
silently corrupt behaviour, and each is pinned by a test:

  * `created_at` is **String**, never TIMESTAMPTZ. Every domain model declares
    `created_at: str` and callers expect the exact ISO-8601 string they wrote to
    come back byte-identically. TIMESTAMPTZ round-trips a `...Z` suffix into
    `...+00:00`. Beyond the broken assertion, silently re-formatting a curator's
    recorded timestamp is precisely the overwrite ALIAS-03 forbids.

  * The `*_json` columns are **Text**, never JSONB. The stores call
    `json.dumps`/`json.loads` themselves; psycopg3 pre-parses JSONB, so
    `json.loads()` would receive an already-parsed `list` and raise. Nothing
    queries *into* the JSON, so JSONB is pure downside here.

  * `id` columns are **String** (uuid4 strings), never native UUID. Every domain
    model declares `id: str`; psycopg would hand back `uuid.UUID` objects and
    break equality across the boundary.

Postgres enforces foreign keys unconditionally, so SQLite's `PRAGMA foreign_keys
= ON` line disappears and the SCHEMA-04 isolation invariant gets STRONGER.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Double,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UserRow(Base):
    """A registered curator (D-06-02).

    The table name stays PLURAL: `USER` (singular) is a RESERVED word in
    PostgreSQL and would need quoting forever. Do not "tidy" it.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    #: An opaque pwdlib/Argon2 hash. NULL for a Google-provisioned account.
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    #: A real BOOLEAN, not SQLite's 0/1 INTEGER -- Postgres rejects the integer
    #: `1` here, so the store's `int(...)`/`bool(...)` casts are gone.
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auth_provider: Mapped[str] = mapped_column(String, nullable=False, default="password")
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class ProfileRow(Base):
    """A learned column mapping for one (field set, source columns) pair (D-01).

    The old `idx_profiles_lookup` index is deliberately NOT recreated: the UNIQUE
    constraint below already creates a btree index on exactly those two columns.
    """

    __tablename__ = "profiles"
    __table_args__ = (UniqueConstraint("field_set_signature", "column_signature"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    field_set_signature: Mapped[str] = mapped_column(String, nullable=False)
    column_signature: Mapped[str] = mapped_column(String, nullable=False)
    mapping_json: Mapped[str] = mapped_column(Text, nullable=False)
    structural_hint_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class FieldSetTemplateRow(Base):
    """A named, reusable field set a curator saved or a preset seeded (D-03)."""

    __tablename__ = "field_set_templates"
    __table_args__ = (Index("idx_field_set_templates_signature", "signature"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    field_set_json: Mapped[str] = mapped_column(Text, nullable=False)
    #: Kept indexed: the UNIQUE on `name` does not cover lookups by signature.
    signature: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class SchemaRow(Base):
    """A governed canonical schema (D-07-02).

    Renamed from `schema` to `canonical_schema`. `SCHEMA` is non-reserved in
    Postgres so the old name would have worked -- this is hygiene, not a bug fix,
    and it is free on a fresh database (D-4). It removes a permanent confusion
    with Postgres's own SCHEMA namespace, `information_schema`, and SQLAlchemy's
    `schema=` kwarg. The DOMAIN class stays `Schema`; only the table moved.
    """

    __tablename__ = "canonical_schema"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class CanonicalFieldRow(Base):
    """One canonical field belonging to exactly one schema (SCHEMA-04)."""

    __tablename__ = "canonical_field"
    __table_args__ = (UniqueConstraint("schema_id", "name"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    #: Replaces SQLite's implicit `rowid`, which does not exist in Postgres.
    #: This column is the ONLY thing that makes `ORDER BY` -- and therefore the
    #: reconstructed `Schema.fields` tuple -- deterministic. Without it Postgres
    #: returns rows in whatever physical order it likes.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    schema_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_schema.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str | None] = mapped_column(String, nullable=True)
    allowed_values_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    #: A real BOOLEAN (see `UserRow.is_verified`).
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    min: Mapped[float | None] = mapped_column(Double, nullable=True)
    max: Mapped[float | None] = mapped_column(Double, nullable=True)
    date_format: Mapped[str | None] = mapped_column(String, nullable=True)


class AliasRow(Base):
    """A vendor's source-column name for a canonical field, with provenance.

    `UNIQUE(canonical_field_id, vendor, source_column)` is what lets the store
    write first-write-wins (`ON CONFLICT DO NOTHING`), making ALIAS-03's
    immutable first-seen provenance a STRUCTURAL invariant rather than a
    conventional one.
    """

    __tablename__ = "alias"
    __table_args__ = (UniqueConstraint("canonical_field_id", "vendor", "source_column"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    #: Replaces SQLite's implicit `rowid` -- see `CanonicalFieldRow.seq`.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    canonical_field_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_field.id"), nullable=False, index=True
    )
    vendor: Mapped[str] = mapped_column(String, nullable=False)
    source_column: Mapped[str] = mapped_column(String, nullable=False)
    provenance_kind: Mapped[str] = mapped_column(String, nullable=False)
    provenance_actor: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
