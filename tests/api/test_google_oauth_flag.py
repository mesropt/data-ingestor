"""Feature-flagged Google OAuth routes (AUTH-02, D-06-05), TDD RED-first
(06-02 Task 2).

The overnight-runnable path: with `DATA_INGESTOR_GOOGLE_OAUTH` unset, both
Google routes return a clear 501, the app imports and starts with NO
SessionMiddleware and NO GOOGLE_CLIENT_ID/SECRET present, and `/api/auth/config`
reports the flag as false (true only when the operator sets it).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client(monkeypatch) -> TestClient:
    from assayingest.api.app import app

    monkeypatch.delenv("DATA_INGESTOR_GOOGLE_OAUTH", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    return TestClient(app)


def test_google_login_returns_501_when_the_flag_is_off(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/api/auth/google/login", follow_redirects=False)
    assert response.status_code == 501
    assert "not enabled" in response.json()["detail"].lower()


def test_google_callback_returns_501_when_the_flag_is_off(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/api/auth/google/callback", follow_redirects=False)
    assert response.status_code == 501
    assert "not enabled" in response.json()["detail"].lower()


def test_config_reflects_the_flag_off_then_on(monkeypatch):
    client = _client(monkeypatch)
    assert client.get("/api/auth/config").json() == {"google_oauth_enabled": False}

    monkeypatch.setenv("DATA_INGESTOR_GOOGLE_OAUTH", "1")
    assert client.get("/api/auth/config").json() == {"google_oauth_enabled": True}


def test_app_imports_and_starts_with_no_session_middleware_when_flag_off(monkeypatch):
    """The overnight default: constructing the app + TestClient succeeds with
    the flag OFF and no GOOGLE secret present, and Starlette's SessionMiddleware
    (needed ONLY for Authlib's OAuth state, and only when the flag is on) is not
    in the middleware stack."""
    from starlette.middleware.sessions import SessionMiddleware

    from assayingest.api.app import app

    client = _client(monkeypatch)
    assert client.get("/api/auth/config").status_code == 200  # app is live
    assert not any(m.cls is SessionMiddleware for m in app.user_middleware)
