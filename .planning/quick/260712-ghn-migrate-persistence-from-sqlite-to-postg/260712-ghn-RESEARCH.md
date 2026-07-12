# Quick Task 260712-ghn: SQLite → PostgreSQL — Research

**Researched:** 2026-07-12
**Domain:** Persistence port (raw `sqlite3` → SQLAlchemy 2.0 + Alembic + Postgres 17)
**Confidence:** HIGH on the schema port and library API shapes (verified against live docs + the actual source). MEDIUM on the test-suite timing estimate.

---

## User Constraints (from CONTEXT.md)

### Locked Decisions — do not revisit
- **D-1:** Postgres runs in **Docker Compose**, `postgres:17`, named volume, healthcheck.
- **D-2:** **Postgres only. SQLite deleted.** No dual impl, no per-env switch, no SQLite-for-tests.
- **D-3:** **SQLAlchemy + Alembic** (ORM + versioned migrations), not raw psycopg.
- **D-4:** **Start clean.** No data-migration script.

### Claude's Discretion
Test fixture strategy; SQLAlchemy style + sync/async; session lifecycle & engine location; whether `_DEFAULT_DB_PATH` is deleted outright (prefer: delete).

### Environment gotcha (verified this session)
Every docker call must be wrapped: `sg docker -c "docker compose up -d"`.
Verified: `Docker Compose version v5.3.0`, `Docker version 29.6.1`. A bare `docker …` fails on the socket.

---

## Summary

The port is mechanically large but architecturally free: all ~33 SQL statements live in exactly four `sqlite_*.py` files, the interfaces contain zero SQL, and the domain is frozen dataclasses. The real risk is **not** in the SQL — it is in three places where SQLite's permissiveness is load-bearing for behaviour the tests assert:

1. **`ORDER BY rowid`** (3 sites in `sqlite_schema_store.py`) — `rowid` does not exist in Postgres. Insertion order of canonical fields and aliases becomes **nondeterministic** unless an explicit ordering column is added. Tests assert alias/field order.
2. **`created_at` as TEXT round-tripped verbatim.** Every domain model declares `created_at: str`, and `tests/test_schema_service.py:217` asserts `nova[0].created_at == "2026-05-05T00:00:00Z"`. Storing this as `TIMESTAMPTZ` re-serialises the `Z` suffix to `+00:00` and **breaks the assertion — and arguably violates ALIAS-03's "provenance is never overwritten"**. `created_at` must stay `TEXT`.
3. **Booleans stored as 0/1.** `int(user.is_verified)` / `int(field.required)` on write and `bool(row[...])` on read. Postgres `BOOLEAN` does **not** coerce integer `1` → `true`; psycopg raises. Both the `int()` casts and the `bool()` casts must be deleted, not kept "for safety".

**Primary recommendation:** ORM entities in a new `persistence/` package + boundary translators (`_entity_to_profile`, preserving today's `_row_to_profile` shape); **session injected into the store constructor**; session-scoped engine + per-test outer transaction with `join_transaction_mode="create_savepoint"` for tests; require an already-running Compose Postgres (**not** testcontainers — it would hit the exact `/var/run/docker.sock` permission wall CONTEXT.md documents).

---

## Standard Stack

All versions verified against the live PyPI JSON API on 2026-07-12.

| Package | Version | Purpose | Provenance |
|---|---|---|---|
| `sqlalchemy` | **2.0.51** (2026-06-15) | ORM + Core | [VERIFIED: pypi.org/pypi/sqlalchemy/json] |
| `alembic` | **1.18.5** (2026-06-25) | Versioned migrations | [VERIFIED: pypi.org/pypi/alembic/json] |
| `psycopg[binary]` | **3.3.4** (2026-05-01) | DBAPI driver (psycopg3) | [VERIFIED: pypi.org/pypi/psycopg/json] |
| `postgres` image | **`postgres:17`** | DB server | [VERIFIED: Docker Hub tag `17`, last updated 2026-07-08 — actively maintained. Tag `18` also exists; D-1 locks 17.] |

**Add to `pyproject.toml` `[project].dependencies`** (not dev — `alembic upgrade head` must work from an install):

```toml
"sqlalchemy>=2.0.51",
"alembic>=1.18.5",
"psycopg[binary]>=3.3.4",
```

### Driver / URL prefix — get this right or you silently install the wrong DBAPI

[CITED: docs.sqlalchemy.org/en/20/dialects/postgresql.html]

| URL prefix | Resolves to | Notes |
|---|---|---|
| `postgresql://` | **psycopg2** | The bare prefix defaults to psycopg2 — the *old* driver. Using it with only `psycopg[binary]` installed → `ModuleNotFoundError: psycopg2`. |
| `postgresql+psycopg://` | **psycopg3** ✅ | **Use this.** Pairs with `pip install psycopg[binary]`. |
| `postgresql+psycopg2://` | psycopg2 | Would require the `psycopg2-binary` package. |

**`DATABASE_URL=postgresql+psycopg://…` — the `+psycopg` is mandatory.**

---

## 1. Exact Schema Port

Six tables. `id` columns stay `String` (uuid4 **strings** — `str(uuid.uuid4())`); do **not** switch to native `UUID`, because every domain model declares `id: str` and psycopg would hand back `uuid.UUID` objects, breaking equality across the boundary. A native-UUID port is a separate, larger change.

`created_at` stays `String` everywhere (see Pitfall 2 — this is not a style choice, it is required by an existing assertion and by ALIAS-03).

### `users` (from `auth/sqlite_store.py`)

| SQLite | Postgres / SQLAlchemy | Hazard |
|---|---|---|
| `id TEXT PRIMARY KEY` | `Mapped[str] = mapped_column(String, primary_key=True)` | — |
| `email TEXT NOT NULL, UNIQUE(email)` | `String, nullable=False, unique=True` | — |
| `password_hash TEXT` | `String, nullable=True` | Argon2 hash from `pwdlib` — carry verbatim, **do not touch the hashing scheme** (CONTEXT). |
| `is_verified INTEGER NOT NULL DEFAULT 0` | **`Boolean, nullable=False, default=False`** | 🔴 **Delete `int(user.is_verified)` on write and `bool(row["is_verified"])` on read.** Postgres rejects `1` for a boolean column. |
| `auth_provider TEXT NOT NULL DEFAULT 'password'` | `String, nullable=False, default="password"` | — |
| `created_at TEXT NOT NULL` | **`String, nullable=False`** — *not* TIMESTAMPTZ | See Pitfall 2. |

Table name `users` is safe. ⚠️ Note: **`USER` (singular) is a RESERVED word in PostgreSQL** and would need quoting — the existing plural name dodges this. Do not "tidy" it to `user`. [VERIFIED: postgresql.org/docs/17/sql-keywords-appendix.html]

Upsert: `ON CONFLICT(email) DO UPDATE SET password_hash, is_verified, auth_provider` (id deliberately **not** updated — a user's stable id survives a credential change).

### `profiles` (from `learning/sqlite_store.py`)

| SQLite | Postgres | Hazard |
|---|---|---|
| `id TEXT PRIMARY KEY` | `String, primary_key=True` | — |
| `field_set_signature TEXT NOT NULL` | `String, nullable=False` | — |
| `column_signature TEXT NOT NULL` | `String, nullable=False` | — |
| `mapping_json TEXT NOT NULL` | **`Text, nullable=False` — keep as TEXT, do NOT use JSONB** | 🔴 The store does `json.dumps()` on write and `json.loads(row[...])` on read. With `JSONB`, psycopg returns an **already-parsed `list`** → `json.loads(list)` raises `TypeError`. JSONB buys nothing here (nothing queries *into* the JSON). If you switch anyway, you must delete both the dumps and the loads. |
| `structural_hint_json TEXT` | `Text, nullable=True` | Same. |
| `created_at TEXT NOT NULL` | `String, nullable=False` | Pitfall 2. |
| `UNIQUE(field_set_signature, column_signature)` | `UniqueConstraint(...)` | — |
| `CREATE INDEX idx_profiles_lookup ON (fs, cs)` | **Drop it** | Redundant: Postgres's UNIQUE constraint already creates a btree index on exactly those columns. |

Upsert: `ON CONFLICT (field_set_signature, column_signature) DO UPDATE SET id, mapping_json, structural_hint_json, created_at`. Updating the PK `id` in the SET clause is legal in Postgres.

### `field_set_templates` (from `learning/sqlite_field_set_store.py`)

`id` String PK · `name` String NOT NULL UNIQUE · `field_set_json` **Text (not JSONB — same dumps/loads reason)** · `signature` String NOT NULL · `created_at` String NOT NULL · index on `signature` (keep — it is *not* covered by the UNIQUE on `name`).
Upsert: `ON CONFLICT (name) DO UPDATE SET id, field_set_json, signature, created_at`.

### `schema` → **rename to `canonical_schema`** (from `learning/sqlite_schema_store.py`)

**`SCHEMA` is *non-reserved* in PostgreSQL** — `CREATE TABLE schema (…)` actually works unquoted. [VERIFIED: postgresql.org/docs/17/sql-keywords-appendix.html] So this is **not** a correctness bug.

**Recommend renaming anyway to `canonical_schema`.** It is free (fresh DB per D-4; the table name appears *only* inside the store file being rewritten; the domain class stays `Schema`), and it removes a permanent confusion with Postgres's own SCHEMA namespace concept, `information_schema`, and SQLAlchemy's `schema=` kwarg on `Table`/`__table_args__`.

Columns: `id` String PK · `name` String NOT NULL UNIQUE · `created_by` String NULL · `created_at` String NOT NULL.

### `canonical_field`

| SQLite | Postgres | Hazard |
|---|---|---|
| `id TEXT PRIMARY KEY` | `String, primary_key=True` | — |
| `schema_id TEXT NOT NULL REFERENCES schema(id)` | `String, ForeignKey("canonical_schema.id"), nullable=False` | ✅ Postgres enforces FKs **always** — the `PRAGMA foreign_keys = ON` line is deleted and the SCHEMA-04 isolation invariant gets *stronger*, not weaker. |
| `required INTEGER NOT NULL DEFAULT 1` | **`Boolean, nullable=False, default=True`** | 🔴 Same as `is_verified`: delete `int(field.required)` and `bool(row["required"])`. |
| `min REAL` / `max REAL` | `Double, nullable=True` (`sqlalchemy.Double`) | — |
| `allowed_values_json TEXT` | `Text` — keep TEXT | Same dumps/loads reason. |
| `name/description/type/unit/date_format TEXT` | `String`/`Text` nullable per current DDL | `type`, `min`, `max`, `unit`, `name`, `description` are all non-reserved in PG. Safe. |
| `UNIQUE(schema_id, name)` | `UniqueConstraint("schema_id", "name")` | — |
| **`ORDER BY rowid`** | 🔴 **`rowid` DOES NOT EXIST** | **Add `seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)` and `ORDER BY seq`.** Without it, `_row_to_schema`'s field order is whatever Postgres feels like — and `tests/test_schema_store.py` asserts field/alias ordering. |

`INSERT OR IGNORE` → `on_conflict_do_nothing(index_elements=["schema_id", "name"])`. Preserves the augment-only P3/D-07-03 invariant.

### `alias`

`id` String PK · `canonical_field_id` String FK→`canonical_field.id` NOT NULL · `vendor`/`source_column`/`provenance_kind`/`provenance_actor` String NOT NULL · `created_at` **String** NOT NULL · `UNIQUE(canonical_field_id, vendor, source_column)` · index on `canonical_field_id` · **`seq` Identity column** (same `ORDER BY a.rowid` problem).

🔴 **`INSERT OR IGNORE` → `on_conflict_do_nothing(...)`, NEVER `on_conflict_do_update`.** This is what makes ALIAS-03 (immutable first-seen provenance) structural rather than conventional. The store's own docstring says so explicitly. Do not "improve" it into an upsert.

### SQLite-permissiveness deltas summary

| SQLite behaviour | Postgres behaviour | Consequence |
|---|---|---|
| `rowid` implicit ordering | no such column | 🔴 nondeterministic order → **add `seq` Identity** |
| `1`/`0` accepted for a boolean-ish INTEGER | `BOOLEAN` rejects `1` | 🔴 delete all `int()`/`bool()` casts |
| dynamic typing: any value into any column | strict types | `min`/`max` must be real floats or NULL |
| `INSERT OR IGNORE` swallows NOT NULL/CHECK violations too | `DO NOTHING` only swallows **unique/exclusion** conflicts | Stricter. FK violations raise in *both*, so no change there. A NOT-NULL violation that SQLite silently skipped would now raise — unlikely (all NOT NULL columns are always supplied) but worth knowing. |
| `CREATE TABLE IF NOT EXISTS` at store construction | DDL owned by Alembic | 🔴 see Pitfall 3 (startup race) |

---

## 2. SQLAlchemy 2.0 + Alembic Wiring (sync engine)

Sync is the right call: the app is single-threaded/synchronous, all four stores are sync, and FastAPI runs sync `def` endpoints in a threadpool. An async port would touch every route. **Do not go async.**

### Layout

```
src/assayingest/persistence/
├── __init__.py
├── base.py       # DeclarativeBase
├── models.py     # the 6 ORM entities (one MetaData → one autogenerate target)
└── engine.py     # create_engine + sessionmaker + get_session()
alembic/
├── env.py
└── versions/
alembic.ini
```

Then `auth/postgres_store.py`, `learning/postgres_store.py`, `learning/postgres_field_set_store.py`, `learning/postgres_schema_store.py` — same neighbourhood as today's `sqlite_*.py`, same `_row_to_X` → `_entity_to_X` boundary-translator shape. **The domain and the four ABCs do not change at all.**

### `persistence/base.py` + `models.py` (2.0 declarative style)

```python
from sqlalchemy import BigInteger, Boolean, Double, ForeignKey, Identity, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auth_provider: Mapped[str] = mapped_column(String, nullable=False, default="password")
    created_at: Mapped[str] = mapped_column(String, nullable=False)  # ISO-8601 verbatim, NOT TIMESTAMPTZ


class AliasRow(Base):
    __tablename__ = "alias"
    __table_args__ = (UniqueConstraint("canonical_field_id", "vendor", "source_column"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    # Replaces SQLite's implicit `rowid` — the ONLY thing that makes ORDER BY deterministic.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    canonical_field_id: Mapped[str] = mapped_column(ForeignKey("canonical_field.id"), nullable=False, index=True)
    vendor: Mapped[str] = mapped_column(String, nullable=False)
    source_column: Mapped[str] = mapped_column(String, nullable=False)
    provenance_kind: Mapped[str] = mapped_column(String, nullable=False)
    provenance_actor: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
```

### `persistence/engine.py` (composition root)

```python
import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..env import load_project_env

_engine = None
_SessionFactory = None


def _database_url() -> str:
    load_project_env()  # override=False — a real env var always wins (quick 260712-ekj)
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Cannot reach the database: DATABASE_URL is not set. "
            "Copy .env.example to .env, then start Postgres with: "
            "sg docker -c 'docker compose up -d db'"
        )
    return url


def get_engine():
    global _engine, _SessionFactory
    if _engine is None:
        _engine = create_engine(
            _database_url(),
            pool_pre_ping=True,          # a container restart kills pooled conns; this reconnects
            connect_args={"connect_timeout": 3},  # never hang for 2 minutes on a dead server
        )
        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one Session per request."""
    get_engine()
    with _SessionFactory() as session:
        yield session
```

`connect_timeout: 3` matters — psycopg's default is effectively the OS TCP timeout (~2 min). Without it, a suite run against a stopped Postgres *hangs* instead of failing.

### Store shape — the session goes in the constructor

```python
class PostgresProfileStore(ProfileStore):
    def __init__(self, session: Session) -> None:
        self._session = session   # NOT an engine, NOT a sessionmaker — see the test note below

    def save(self, profile: LearnedProfile) -> None:
        stmt = insert(ProfileRow).values(...)          # sqlalchemy.dialects.postgresql.insert
        stmt = stmt.on_conflict_do_update(
            index_elements=["field_set_signature", "column_signature"],
            set_={
                "id": stmt.excluded.id,
                "mapping_json": stmt.excluded.mapping_json,
                "structural_hint_json": stmt.excluded.structural_hint_json,
                "created_at": stmt.excluded.created_at,
            },
        )
        self._session.execute(stmt)
        self._session.commit()
```

> ⚠️ **Load-bearing:** the store must hold a **`Session`**, not an engine or a sessionmaker. If a store opens its own connection per method, it checks out a *different* pooled connection, lands outside the test's transaction, and the SAVEPOINT-rollback fixture below silently stops isolating anything. This single design choice is what makes fast tests possible.

`session.commit()` inside the store preserves today's semantics (`store.save(p)` then `store.find(...)` in a fresh call must see the row) **and** still works under the rollback fixture — see below.

### `api/deps.py`

```python
def get_profile_store(session: Session = Depends(get_session)) -> ProfileStore:
    return PostgresProfileStore(session)
```

Same for `get_field_set_store`, `get_schema_store`, `get_user_store`. Existing tests that override `get_profile_store` with a concrete store keep working unchanged in shape.

### Alembic

```bash
uv run alembic init alembic          # then edit env.py per below
uv run alembic revision --autogenerate -m "initial schema"
uv run alembic upgrade head
```

`alembic/env.py` — **build the engine directly; do not round-trip the URL through `alembic.ini`:**

```python
from sqlalchemy import create_engine
from assayingest.env import load_project_env
from assayingest.persistence.base import Base
from assayingest.persistence import models  # noqa: F401 — import for side effect: registers all 6 tables

target_metadata = Base.metadata


def run_migrations_online() -> None:
    load_project_env()
    url = os.environ["DATABASE_URL"]
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
```

🔴 **Pitfall:** the scaffolded `env.py` uses `config.set_main_option("sqlalchemy.url", url)` + `engine_from_config`. That path runs the URL through ConfigParser, which treats `%` as interpolation — a password containing `%` raises `InterpolationSyntaxError`. Building the engine directly from `os.environ` sidesteps it entirely.

🔴 **Also:** without `import models`, `Base.metadata` is empty and `--autogenerate` cheerfully produces an **empty migration**. Verify the generated file actually contains six `op.create_table` calls before committing it.

---

## 3. Test Fixture Strategy — the crux

**Today:** 620 passed / 4 skipped in ~24s. No `conftest.py` exists. 23 test files construct stores directly, ~40 call sites of the form `SqliteProfileStore(tmp_path / "profiles.db")`.

### Options

| Option | Per-test cost | Isolation | Verdict |
|---|---|---|---|
| **Session-scoped DB + per-test outer txn + `join_transaction_mode="create_savepoint"`** | **~sub-ms** (SAVEPOINT/ROLLBACK only) | Full | ✅ **RECOMMENDED** |
| CREATE/DROP schema per test | ~10–50ms DDL × ~200 store tests → **+2–10s** | Full | Slower for no gain |
| `CREATE DATABASE … TEMPLATE` per test | ~50–200ms → **+10s–1min** | Full | Too slow per-test. Genuinely useful only for *one DB per xdist worker*. |
| **testcontainers-python** | ~2–5s startup + image pull | Full | ❌ **Reject — see below** |
| Require an already-running Compose service | 0 | — | ✅ pairs with the recommendation |

### Why NOT testcontainers (environment-specific, decisive)

`testcontainers` drives the Docker daemon through the Python `docker` SDK, which talks to `/var/run/docker.sock` **directly**. CONTEXT.md documents (verified) that this shell's session predates the `docker` group membership, so anything touching the socket without the `sg docker -c "…"` wrapper fails with `permission denied`. A test-suite import cannot re-exec itself under `sg`. **testcontainers would fail on this exact machine**, and it also duplicates D-1's already-locked "Postgres runs in Compose" decision. Require the Compose service instead.

### Recommended `tests/conftest.py`

This is the official SQLAlchemy 2.0 test recipe. [VERIFIED: docs.sqlalchemy.org/en/20/orm/session_transaction.html — "Joining a Session into an External Transaction (such as for test suites)"]. The docs explicitly note that in 2.0 the old event-listener "restart savepoint" recipe **is no longer required**.

```python
import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from assayingest.persistence.base import Base
from assayingest.persistence import models  # noqa: F401

_TEST_URL = os.environ.get(
    "DATABASE_URL_TEST",
    "postgresql+psycopg://assayingest:assayingest@localhost:5432/assayingest_test",
)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(_TEST_URL, connect_args={"connect_timeout": 3})
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # fail LOUDLY, never skip, never hang
        raise pytest.UsageError(
            f"PostgreSQL is not reachable at {_TEST_URL!r} -- the test suite cannot run.\n"
            f"Start it with:  sg docker -c 'docker compose up -d db'\n"
            f"Underlying error: {exc}"
        ) from exc
    Base.metadata.create_all(eng)   # once per session
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine):
    """Every test runs inside an outer transaction that is ALWAYS rolled back.

    join_transaction_mode="create_savepoint" lets the store call session.commit()
    (which it must, to preserve today's write-then-read semantics) while the outer
    transaction stays open -- so the rollback below still wipes everything.
    """
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    trans.rollback()
    connection.close()


@pytest.fixture
def profile_store(db_session):
    return PostgresProfileStore(db_session)
# ... likewise schema_store / field_set_store / user_store
```

**Failure mode when Postgres is down:** `pytest.UsageError` from a session-scoped fixture → the run aborts immediately with the actionable message above. It does **not** hang (`connect_timeout=3`) and it does **not** silently skip (never use `pytest.skip` here — a green suite that tested nothing is the worst outcome and would violate the "no weakened assertions" rule).

**Use a separate database** (`assayingest_test`), not the dev DB — `create_all` at session start would otherwise touch dev data.

**Expected cost:** the ~400 tests that never touch a store are unaffected. The ~200 that do gain a network round-trip per statement over a local loopback socket (tens of µs). Estimate **24s → 30–40s**. [ASSUMED — an estimate, not measured; validate during execution.]

### Test churn the planner must budget for

- **~40 call sites** `Sqlite*Store(tmp_path / "…")` → `…Store(db_session)` (or the `profile_store` fixture). Mechanical.
- **2 tests assert on the DB file itself** and must be rewritten or deleted (they are meaningless under Postgres):
  - `tests/test_profile_store.py::test_sqlite_store_creates_the_db_file_and_parent_dir_on_construction`
  - `tests/test_schema_store.py::test_store_creates_the_db_file_and_parent_dir_on_construction`
- **2 tests open `sqlite3.connect(db_path)` directly** to prove parameterised queries (the `'; DROP TABLE …; --` round-trip, ASVS V5). **Keep these tests — port them**, do not delete: swap the raw `sqlite3` assertion for `db_session.execute(text("SELECT COUNT(*) FROM profiles")).scalar() == 1`. They are the security proof.
  - `tests/test_profile_store.py:159`, `tests/test_schema_store.py:206`
- CLI `--profiles-db PATH` flag (`cli.py:723`) is meaningless — drop it (or replace with `--database-url`), and update README.

---

## 4. Docker Compose

No `docker-compose.yml` exists yet. `.env.example` does.

```yaml
# docker-compose.yml -- no top-level `version:` key; Compose v5 treats it as obsolete.
services:
  db:
    image: postgres:17
    container_name: data-ingestor-db
    environment:
      POSTGRES_USER: assayingest
      POSTGRES_PASSWORD: assayingest      # dev-only, non-secret, committed on purpose
      POSTGRES_DB: assayingest
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      # -U/-d matter: bare `pg_isready` checks the *server*, which reports ready
      # during init BEFORE the app database exists. This gates on the real thing.
      test: ["CMD-SHELL", "pg_isready -U assayingest -d assayingest"]
      interval: 2s
      timeout: 3s
      retries: 15
      start_period: 5s

volumes:
  pgdata:
```

Create the test database once (the image only auto-creates `POSTGRES_DB`):

```bash
sg docker -c "docker compose exec -T db createdb -U assayingest assayingest_test"
```

**Credentials pattern:** dev defaults live in `docker-compose.yml` + `.env.example` as non-secret literals. The real `DATABASE_URL` goes in the gitignored `.env`, which already holds `ANTHROPIC_API_KEY` — **never read, echo, or commit that file.**

`.env.example` additions:
```
DATABASE_URL=postgresql+psycopg://assayingest:assayingest@localhost:5432/assayingest
DATABASE_URL_TEST=postgresql+psycopg://assayingest:assayingest@localhost:5432/assayingest_test
```

---

## 5. Pitfalls

### Pitfall 1 — 🔴 `ORDER BY rowid` has no Postgres equivalent
Three sites in `sqlite_schema_store.py` (lines 167, 222, 244). Postgres has no `rowid`; the query simply fails to compile, and "fixing" it by dropping the ORDER BY makes canonical-field and alias order **nondeterministic** — quietly breaking `test_schema_store.py`'s order assertions and the reconstructed `Schema.fields` tuple. **Fix:** add a `seq BIGINT GENERATED BY DEFAULT AS IDENTITY` column to `canonical_field` and `alias`, and `ORDER BY seq`.

### Pitfall 2 — 🔴 `created_at` must stay TEXT, not TIMESTAMPTZ
Every domain model declares `created_at: str` (`auth/models.py`, `domain/models.py` `Alias`/`Schema`, `learning/profile.py`). Callers pass ISO-8601 strings and expect them back **byte-identically**. Verified break:

```
tests/test_schema_service.py:217
    assert nova[0].created_at == "2026-05-05T00:00:00Z"
```

Round-tripped through `TIMESTAMPTZ`, that value comes back as a `datetime`, whose `.isoformat()` is `"2026-05-05T00:00:00+00:00"` — **not equal**. Also `tests/test_schema_store.py:152,176` assert exact `+00:00` strings. Beyond the tests: ALIAS-03 says first-seen provenance is *never* overwritten, and silently re-formatting a curator's recorded timestamp is exactly that. **Store `created_at` as `String`.** (Converting the domain to `datetime` is a legitimate future refactor — it is not this task.)

### Pitfall 3 — 🔴 Startup preset-seeding races the migration, and the race is *silent*
`api/app.py::_lifespan` calls `seed_presets(factory())` → `store.list()` → `SELECT … FROM field_set_templates`. If Alembic has not run, Postgres raises `UndefinedTable`. The lifespan wraps it in `except Exception` and only **logs a warning** (deliberately, per T-e0e-03: seeding must not brick the server). Net result: **the app starts, the field-set picker is blank, and "Upload & Map" is a silent no-op** — regressing exactly what quick task 260712-e0e fixed.

Today this cannot happen, because each store's constructor runs `CREATE TABLE IF NOT EXISTS`. Under Alembic, stores no longer create tables, so that safety net disappears.

**Recommendation:** keep the broad catch around *seeding* (a malformed preset YAML still must not brick the server), but add an explicit startup check that **raises** — connect, and assert the `alembic_version` table is at head. A missing schema is a deployment error, not a seeding hiccup, and it must be loud. Document `alembic upgrade head` as a required step in README/Quickstart (or wire it into the app's start command).

### Pitfall 4 — 🔴 Boolean columns reject `0`/`1`
`int(user.is_verified)`, `int(field.required)` on write; `bool(row["is_verified"])`, `bool(row["required"])` on read. Postgres `BOOLEAN` does not coerce an integer. Delete all four casts. Leaving the `bool()` on the read path is harmless-but-dead; leaving the `int()` on the write path **raises**.

### Pitfall 5 — 🔴 `postgresql://` silently means psycopg2
See the driver table above. With only `psycopg[binary]` installed, a bare `postgresql://` URL fails at engine creation with `ModuleNotFoundError: No module named 'psycopg2'` — a confusing error that looks like a missing dependency rather than a wrong URL. **`postgresql+psycopg://`.**

### Pitfall 6 — JSON columns: `json.loads()` on an already-parsed value
If you switch any `*_json TEXT` column to `JSONB`, psycopg3 deserialises it **for you**. The existing `json.loads(row["mapping_json"])` then receives a `list` and raises `TypeError: the JSON object must be str, bytes or bytearray`. Keep them `Text`. Nothing queries inside the JSON, so JSONB is pure downside here.

### Pitfall 7 — `INSERT OR IGNORE` → `DO NOTHING`, never `DO UPDATE`
`add_alias` and `_insert_missing_fields` rely on first-write-wins to enforce ALIAS-03 (immutable provenance) and P3/D-07-03 (augment-only, never overwrite). `on_conflict_do_nothing(...)` preserves this. An `on_conflict_do_update` — the "obvious" symmetric choice, and the one used by the *other three* stores — would silently destroy both invariants. The four stores are deliberately asymmetric here.

### Pitfall 8 — the store must hold a `Session`, not an engine
Restated because it is the single easiest way to end up with a green-but-non-isolating test suite: a store that opens its own connection per method escapes the test's outer transaction, and `trans.rollback()` then rolls back nothing. Rows leak between tests and the failures look random.

### Pitfall 9 — connection timeout
Without `connect_args={"connect_timeout": 3}`, a run against a stopped container blocks on the OS TCP timeout (~2 min) before failing. Set it on both the app engine and the test engine.

---

## Files the executor will touch

| File | Change |
|---|---|
| `src/assayingest/auth/sqlite_store.py` | → `postgres_store.py` (delete) |
| `src/assayingest/learning/sqlite_store.py` | → `postgres_store.py` (delete; also deletes `_DEFAULT_DB_PATH`, imported by 3 other modules) |
| `src/assayingest/learning/sqlite_field_set_store.py` | → `postgres_field_set_store.py` (delete) |
| `src/assayingest/learning/sqlite_schema_store.py` | → `postgres_schema_store.py` (delete) |
| `src/assayingest/persistence/{base,models,engine}.py` | **new** |
| `alembic/`, `alembic.ini` | **new** |
| `src/assayingest/api/deps.py` | 4 factories take `Depends(get_session)` |
| `src/assayingest/api/app.py` | add loud startup schema check (Pitfall 3) |
| `src/assayingest/cli.py` | drop `--profiles-db` + `_resolve_store`'s path arg (lines 251-258, 723-728) |
| `tests/conftest.py` | **new** — engine + `db_session` + store fixtures |
| 23 test files | ~40 store-construction call sites; 2 file-existence tests deleted; 2 raw-`sqlite3` security tests **ported, not deleted** |
| `docker-compose.yml`, `.env.example`, `README.md`, `pyproject.toml` | new / updated |
| `.gitignore`, `.assayingest/` | remove the now-dead SQLite dir |

---

## Assumptions Log

| # | Claim | Risk if wrong |
|---|---|---|
| A1 | Suite goes 24s → ~30–40s | Low. If it lands much worse, the fixture is leaking connections or a store is opening its own. |
| A2 | ~200 of the 620 tests touch a store | Low — affects the estimate only. |
| A3 | No `%` in the dev password, so the ConfigParser interpolation pitfall is latent, not live | Low — the recommended `env.py` avoids it regardless. |

## Open Questions

1. **Does the loud-startup-check contradict T-e0e-03 ("seeding must not brick the server")?** No — they are different failures: a missing *schema* is a deployment error (must be loud); a bad *preset YAML* is a data hiccup (must not brick). But the planner should make this an explicit decision, since it does add a new hard-failure path to app startup.

## Sources

**HIGH confidence (verified this session):**
- Actual source: all 4 `sqlite_*.py` stores, `api/deps.py`, `api/app.py`, `env.py`, `learning/seed.py`, `cli.py`, domain models, 23 test files.
- PyPI JSON API — sqlalchemy 2.0.51, alembic 1.18.5, psycopg 3.3.4 (dates confirmed).
- Docker Hub tags API — `postgres:17` current, updated 2026-07-08.
- `sg docker -c "docker compose version"` → v5.3.0 / Docker 29.6.1.
- docs.sqlalchemy.org/en/20/orm/session_transaction.html — `join_transaction_mode="create_savepoint"` recipe; event listeners no longer needed in 2.0.
- postgresql.org/docs/17/sql-keywords-appendix.html — `SCHEMA` non-reserved, `USER` **reserved**.

**MEDIUM:**
- docs.sqlalchemy.org/en/20/dialects/postgresql.html — URL prefixes / default DBAPI.
