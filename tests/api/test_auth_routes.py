"""Email/password auth routes (AUTH-01/03) + /api/auth/config (AUTH-02),
TDD RED-first (06-02 Task 1).

Exercises the HTTP surface plan 06-01's substrate underlies: signup mints a
verification token and logs the SPA verification link (the dev "email" is the
server console, D-06-04); login sets the itsdangerous-signed di_session cookie
that round-trips through TestClient; verify consumes the token and flips
is_verified; config reports the (off-by-default) Google flag.

Every test injects a tmp-path `SqliteUserStore` via
`app.dependency_overrides[get_user_store]` so no test ever touches the real
demo DB (mirrors `test_upload.py`'s `get_profile_store` override), and sets a
throwaway `SESSION_SECRET` so the cookie/token seams can sign.
"""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from assayingest.auth.sqlite_store import SqliteUserStore


def _client(tmp_path, monkeypatch) -> tuple[TestClient, SqliteUserStore]:
    from assayingest.api.app import app
    from assayingest.api.deps import get_user_store

    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-not-a-real-one")
    monkeypatch.delenv("DATA_INGESTOR_GOOGLE_OAUTH", raising=False)
    store = SqliteUserStore(tmp_path / "users.db")
    app.dependency_overrides[get_user_store] = lambda: store
    return TestClient(app), store


def _clear() -> None:
    from assayingest.api.app import app

    app.dependency_overrides.clear()


# --- signup -------------------------------------------------------------------


def test_signup_creates_user_returns_201_and_logs_the_console_verification_link(
    tmp_path, monkeypatch, caplog
):
    client, store = _client(tmp_path, monkeypatch)
    with caplog.at_level(logging.INFO, logger="assayingest.auth"):
        response = client.post(
            "/api/auth/signup",
            json={"email": "curator@example.com", "password": "hunter2hunter"},
        )
    _clear()

    assert response.status_code == 201
    body = response.json()
    assert "console" in body["message"].lower()

    created = store.get_by_email("curator@example.com")
    assert created is not None
    assert created.is_verified is False
    assert created.auth_provider == "password"
    assert created.password_hash is not None
    assert created.password_hash != "hunter2hunter"  # never stored in plaintext

    logged = " ".join(rec.getMessage() for rec in caplog.records)
    assert "verify?token=" in logged  # the SPA landing link, D-06-04 console "email"
    # the token itself is present after the '=' (non-empty)
    token_part = logged.split("verify?token=", 1)[1].split()[0]
    assert len(token_part) > 0


def test_signup_with_a_short_password_returns_422_and_creates_no_user(
    tmp_path, monkeypatch
):
    client, store = _client(tmp_path, monkeypatch)
    response = client.post(
        "/api/auth/signup",
        json={"email": "shorty@example.com", "password": "short"},  # < 8 chars
    )
    _clear()

    assert response.status_code == 422
    assert store.get_by_email("shorty@example.com") is None


def test_signup_with_an_already_registered_email_returns_409_and_no_duplicate(
    tmp_path, monkeypatch
):
    client, store = _client(tmp_path, monkeypatch)
    first = client.post(
        "/api/auth/signup",
        json={"email": "dup@example.com", "password": "hunter2hunter"},
    )
    assert first.status_code == 201
    original = store.get_by_email("dup@example.com")

    second = client.post(
        "/api/auth/signup",
        json={"email": "dup@example.com", "password": "different-pw-here"},
    )
    _clear()

    assert second.status_code == 409
    assert "already registered" in second.json()["detail"].lower()
    # same row, unchanged (no upsert-over of the existing account)
    assert store.get_by_email("dup@example.com").id == original.id
    assert store.get_by_email("dup@example.com").password_hash == original.password_hash


# --- login --------------------------------------------------------------------


def test_login_with_correct_credentials_sets_cookie_that_round_trips_to_me(
    tmp_path, monkeypatch
):
    client, _store = _client(tmp_path, monkeypatch)
    client.post(
        "/api/auth/signup",
        json={"email": "curator@example.com", "password": "hunter2hunter"},
    )

    login = client.post(
        "/api/auth/login",
        json={"email": "curator@example.com", "password": "hunter2hunter"},
    )
    assert login.status_code == 200
    assert "di_session" in login.cookies

    # The same TestClient carries the cookie forward: /api/auth/me resolves it.
    me = client.get("/api/auth/me")
    _clear()

    assert me.status_code == 200
    assert me.json()["email"] == "curator@example.com"


def test_login_with_a_wrong_password_returns_401_and_sets_no_cookie(
    tmp_path, monkeypatch
):
    client, store = _client(tmp_path, monkeypatch)
    client.post(
        "/api/auth/signup",
        json={"email": "curator@example.com", "password": "hunter2hunter"},
    )

    login = client.post(
        "/api/auth/login",
        json={"email": "curator@example.com", "password": "wrong-password"},
    )
    _clear()

    assert login.status_code == 401
    assert "di_session" not in login.cookies
    # the just-signed-up user still exists (a failed login mutates nothing)
    assert store.get_by_email("curator@example.com") is not None


def test_an_unverified_user_can_still_log_in(tmp_path, monkeypatch):
    """D-06-04: sign-in is allowed pre-verification; only governed actions
    are blocked until the email is verified."""
    client, store = _client(tmp_path, monkeypatch)
    client.post(
        "/api/auth/signup",
        json={"email": "unverified@example.com", "password": "hunter2hunter"},
    )
    assert store.get_by_email("unverified@example.com").is_verified is False

    login = client.post(
        "/api/auth/login",
        json={"email": "unverified@example.com", "password": "hunter2hunter"},
    )
    _clear()

    assert login.status_code == 200
    assert "di_session" in login.cookies


# --- verify -------------------------------------------------------------------


def test_verify_with_a_fresh_token_marks_the_user_verified(
    tmp_path, monkeypatch, caplog
):
    client, store = _client(tmp_path, monkeypatch)
    with caplog.at_level(logging.INFO, logger="assayingest.auth"):
        client.post(
            "/api/auth/signup",
            json={"email": "curator@example.com", "password": "hunter2hunter"},
        )
    logged = " ".join(rec.getMessage() for rec in caplog.records)
    token = logged.split("verify?token=", 1)[1].split()[0]

    response = client.get("/api/auth/verify", params={"token": token})
    _clear()

    assert response.status_code == 200
    assert response.json()["status"] == "verified"
    assert store.get_by_email("curator@example.com").is_verified is True


def test_verify_with_a_garbage_token_reports_expired_and_verifies_no_one(
    tmp_path, monkeypatch
):
    client, store = _client(tmp_path, monkeypatch)
    client.post(
        "/api/auth/signup",
        json={"email": "curator@example.com", "password": "hunter2hunter"},
    )

    response = client.get("/api/auth/verify", params={"token": "not-a-real-token"})
    _clear()

    assert response.status_code == 200
    assert response.json()["status"] == "expired"
    assert store.get_by_email("curator@example.com").is_verified is False


# --- logout -------------------------------------------------------------------


def test_logout_clears_the_session_cookie(tmp_path, monkeypatch):
    client, _store = _client(tmp_path, monkeypatch)
    client.post(
        "/api/auth/signup",
        json={"email": "curator@example.com", "password": "hunter2hunter"},
    )
    client.post(
        "/api/auth/login",
        json={"email": "curator@example.com", "password": "hunter2hunter"},
    )

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    # The Set-Cookie clears di_session (empty value / expiry in the past).
    set_cookie = logout.headers.get("set-cookie", "")
    assert "di_session=" in set_cookie

    # After logout, the client's jar no longer resolves a signed-in user.
    me = client.get("/api/auth/me")
    _clear()
    assert me.status_code == 401


# --- config -------------------------------------------------------------------


def test_config_reports_google_oauth_disabled_by_default(tmp_path, monkeypatch):
    client, _store = _client(tmp_path, monkeypatch)
    response = client.get("/api/auth/config")
    _clear()

    assert response.status_code == 200
    assert response.json() == {"google_oauth_enabled": False}
