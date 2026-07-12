"""The LOUD startup schema check (quick 260712-ghn, TRAP 3).

Under Alembic the stores no longer run `CREATE TABLE IF NOT EXISTS`, so nothing
creates the tables implicitly. Without `_require_schema_at_head`, an unmigrated
database would let `seed_presets` raise `UndefinedTable`, `_lifespan`'s deliberate
`except Exception` would log it as a mere WARNING, and the app would boot with an
empty field-set picker and an "Upload and Map" button that silently does nothing --
regressing exactly what quick task 260712-e0e fixed.

Two rules must hold SIMULTANEOUSLY, and these tests pin both:
  * a missing SCHEMA is a deployment error  -> LOUD, refuse to start;
  * a malformed preset YAML is a data hiccup -> warn, start anyway (T-e0e-03).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from assayingest.api.app import app
from assayingest.learning import seed as seed_module
from assayingest.persistence import engine as engine_module


def test_startup_raises_when_the_database_has_no_alembic_revision(db_session):
    # Emptying `alembic_version` is the in-transaction equivalent of an unmigrated
    # database. It is rolled back with the test, so the shared test database is
    # untouched.
    db_session.execute(text("DELETE FROM alembic_version"))
    db_session.commit()

    with pytest.raises(RuntimeError) as exc:
        with TestClient(app):
            pass

    # The message must name the FIX, not the symptom.
    assert "alembic upgrade head" in str(exc.value)


def test_startup_raises_when_the_database_is_unreachable():
    # A schema that cannot even be read is a deployment error, never a warning.
    dead = create_engine(
        "postgresql+psycopg://assayingest:assayingest@localhost:5432/no_such_database",
        connect_args={"connect_timeout": 3},
    )
    engine_module.set_session_factory(sessionmaker(bind=dead))

    with pytest.raises(RuntimeError) as exc:
        with TestClient(app):
            pass

    message = str(exc.value)
    assert "docker compose up -d db" in message
    assert "alembic upgrade head" in message


def test_a_bad_preset_yaml_still_does_not_brick_the_server(monkeypatch, caplog):
    # The OTHER half of TRAP 3, and the reason the schema check sits OUTSIDE the
    # seeding try/except rather than inside a single widened one. A broken preset must
    # warn and let the app start (T-e0e-03) -- only a missing SCHEMA is fatal.
    def _explode():
        raise ValueError("preset yaml is malformed")

    monkeypatch.setattr(seed_module, "load_presets", _explode)

    with TestClient(app) as client:  # must NOT raise
        response = client.get("/api/field-sets")

    assert response.status_code == 200
    assert "Starter field sets are unavailable" in caplog.text
