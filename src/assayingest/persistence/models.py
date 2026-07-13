"""The ORM entities -- the ONLY place this project describes its tables.

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

  * `removed_at` (D-10-15 tombstone columns, `CanonicalFieldRow`/`AliasRow`)
    follows the SAME rule as `created_at`: a **String** ISO-8601 timestamp,
    never TIMESTAMPTZ. Re-formatting a recorded removal timestamp is exactly
    the overwrite ALIAS-03 forbids -- do not "modernize" this to TIMESTAMPTZ.

Postgres enforces foreign keys unconditionally, so the old `PRAGMA foreign_keys
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
    text,
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
    #: A real BOOLEAN, not the old 0/1 INTEGER -- Postgres rejects the integer
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
    #: The human's vendor assertion at confirm time (10-09/INGEST-02).
    #: Nullable is honest, not lazy: every profile saved before this column
    #: existed genuinely has no recorded vendor, and there is no backfill --
    #: nothing truthful to backfill it with.
    vendor: Mapped[str | None] = mapped_column(String, nullable=True)


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

    `removed_at`/`removed_by` are the D-10-15 tombstone columns, now extended to
    the SCHEMA itself: deleting a Schema never issues a DELETE. It would take its
    canonical fields, and with them every alias the crosswalk ever learned --
    each carrying who recorded it and when -- and destroy the lot with no trace
    that they had existed. The tombstone keeps the audit trail and keeps every
    already-exported dataset's target explicable after the fact.

    The UNIQUE on `name` is therefore PARTIAL (`uq_canonical_schema_live`,
    `WHERE removed_at IS NULL`), exactly as it is for a field: a tombstoned
    Schema must not permanently occupy its name, or the curator could never
    re-create a Schema they deleted by mistake.
    """

    __tablename__ = "canonical_schema"
    __table_args__ = (
        Index(
            "uq_canonical_schema_live",
            "name",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    removed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    removed_by: Mapped[str | None] = mapped_column(String, nullable=True)


class CanonicalFieldRow(Base):
    """One canonical field belonging to exactly one schema (SCHEMA-04).

    `removed_at`/`removed_by` are the D-10-15 tombstone columns: removing a
    field NEVER issues a DELETE, it marks the row removed (who + when) and
    keeps it for the audit trail. The UNIQUE on `(schema_id, name)` is
    therefore PARTIAL (`uq_canonical_field_live`, `WHERE removed_at IS NULL`)
    -- a tombstoned row must not permanently occupy its name, or a re-added
    field would be swallowed by `ON CONFLICT DO NOTHING` and become invisible
    forever (T-10-09).
    """

    __tablename__ = "canonical_field"
    __table_args__ = (
        Index(
            "uq_canonical_field_live",
            "schema_id",
            "name",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    #: Replaces the previous store's implicit `rowid`, which Postgres has no
    #: equivalent of.
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
    #: D-10-15 tombstone -- String ISO-8601, never TIMESTAMPTZ (see module docstring).
    removed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    removed_by: Mapped[str | None] = mapped_column(String, nullable=True)


class PendingUploadRow(Base):
    """One review-ready pending upload, keyed by its `upload_token` -- what
    lets a curator's open Review screen survive a server restart, a
    `--reload` cycle, or a worker switch (the confirm-after-deploy defect).

    PRIVACY DECISION (deliberate, quick 260712): `entry_json` contains the
    uploaded file's CELL VALUES at rest -- previously they lived only in
    process memory. That is acceptable ONLY because a row here is transient
    by construction: it carries `expires_at` (a TTL enforced by
    `api.state.UploadRegistry` -- expired rows are deleted on lookup and
    swept on every persist), and a successful `/api/confirm` purges it
    immediately. A pending upload's rows must never outlive the review they
    exist for. `headers_only` keeps its exact meaning -- it restricts what
    CLAUDE sees, never what the server itself reads or retains; confirm
    still validates real cell values either way.

    `created_at`/`expires_at` are **String** ISO-8601 (fixed-width UTC, so
    lexicographic order IS chronological order and the expiry sweep can be a
    plain SQL string comparison) -- the same rule as every other timestamp
    column here, never TIMESTAMPTZ. `entry_json` is **Text**, never JSONB
    (see module docstring). `token` is the uuid4 string minted by
    `UploadRegistry.put`, so it is the natural primary key.
    """

    __tablename__ = "pending_uploads"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    entry_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    #: Indexed: the lazy TTL sweep deletes `WHERE expires_at <= now` on every
    #: persist, and must not scan the table to do it.
    expires_at: Mapped[str] = mapped_column(String, nullable=False, index=True)


class AliasRow(Base):
    """A vendor's source-column name for a canonical field, with provenance.

    `UNIQUE(canonical_field_id, vendor, source_column)` is what lets the store
    write first-write-wins (`ON CONFLICT DO NOTHING`), making ALIAS-03's
    immutable first-seen provenance a STRUCTURAL invariant rather than a
    conventional one.

    `removed_at`/`removed_by` are the D-10-15 tombstone columns -- same rule as
    `CanonicalFieldRow`'s: never a DELETE, and the UNIQUE constraint above is
    replaced by a PARTIAL unique index (`uq_alias_live`, `WHERE removed_at IS
    NULL`) so a tombstoned alias never blocks re-adding the same (vendor,
    source_column) pair (T-10-09).
    """

    __tablename__ = "alias"
    __table_args__ = (
        Index(
            "uq_alias_live",
            "canonical_field_id",
            "vendor",
            "source_column",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    #: Replaces the previous store's implicit `rowid` -- see `CanonicalFieldRow.seq`.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    canonical_field_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_field.id"), nullable=False, index=True
    )
    vendor: Mapped[str] = mapped_column(String, nullable=False)
    source_column: Mapped[str] = mapped_column(String, nullable=False)
    provenance_kind: Mapped[str] = mapped_column(String, nullable=False)
    provenance_actor: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    #: D-10-15 tombstone -- String ISO-8601, never TIMESTAMPTZ (see module docstring).
    removed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    removed_by: Mapped[str | None] = mapped_column(String, nullable=True)
