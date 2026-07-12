"""Swagger/ReDoc/OpenAPI relocation off `/docs` (quick task 260712-fuf).

Once the frontend routes tabs on clean paths instead of a hash, `/docs`
collides with FastAPI's built-in Swagger UI -- the app's own Docs tab can
never own that path while FastAPI keeps registering an explicit path
operation there. This regression test pins the fix: the three docs
endpoints move under `/api`, and `/docs` falls through to
`app.frontend()`'s SPA catch-all (already registered, RESEARCH.md
Pattern 3) instead of Swagger.

Uses a bare `TestClient(app)` (no `with` block) so the lifespan does not
run and no preset seeding fires -- the lighter idiom already used across
`tests/api/` (see `test_confirm_gate.py`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from assayingest.api.app import app

client = TestClient(app)

# frontend/dist is a gitignored build artifact (`npm run build` output) --
# a fresh checkout that has not built the frontend has no SPA shell to
# serve, so the assertion on its *content* would be meaningless there.
_DIST_INDEX = Path(__file__).resolve().parents[2] / "frontend" / "dist" / "index.html"


def test_swagger_relocated_to_api_docs():
    response = client.get("/api/docs")
    assert response.status_code == 200
    assert "swagger-ui" in response.text


def test_redoc_relocated_to_api_redoc():
    response = client.get("/api/redoc")
    assert response.status_code == 200


def test_openapi_schema_relocated_to_api_openapi_json():
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert "openapi" in response.json()


def test_docs_path_is_no_longer_swagger():
    """The regression this whole task exists to prevent: `/docs` must not
    serve Swagger, whether or not a built SPA exists on disk."""
    response = client.get("/docs")
    assert "swagger-ui" not in response.text


@pytest.mark.skipif(
    not _DIST_INDEX.exists(),
    reason="frontend/dist is a gitignored build artifact; run `npm run build` first",
)
def test_docs_path_falls_through_to_the_spa_shell():
    response = client.get("/docs")
    assert response.status_code == 200
    assert '<div id="root">' in response.text
