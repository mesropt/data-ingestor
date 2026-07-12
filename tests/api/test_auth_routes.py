"""Email/password auth routes (AUTH-01/03) + /api/auth/config (AUTH-02),
TDD RED-first (06-02 Task 1).

Exercises the HTTP surface plan 06-01's substrate underlies: signup mints a
verification token and logs the SPA verification link (the dev "email" is the
server console, D-06-04); login sets the itsdangerous-signed di_session cookie
that round-trips through TestClient; verify consumes the token and flips
is_verified; config reports the (off-by-default) Google flag.

Every test runs against a `PostgresUserStore` on the harness's rolled-back test
connection, so no test ever touches the real demo database, and sets a throwaway
`SESSION_SECRET` so the cookie/token seams can sign.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient



def _client(monkeypatch, user_store) -> tuple[TestClient, object]:
    from assayingest.api.app import app
    from assayingest.api.deps import get_user_store

    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-not-a-real-one")
    monkeypatch.delenv("DATA_INGESTOR_GOOGLE_OAUTH", raising=False)
    app.dependency_overrides[get_user_store] = lambda: user_store
    return TestClient(app), user_store


def _clear() -> None:
    from assayingest.api.app import app

    app.dependency_overrides.clear()


# --- signup -------------------------------------------------------------------


def test_signup_creates_user_returns_201_and_logs_the_console_verification_link(monkeypatch, caplog, user_store):
    client, store = _client(monkeypatch, user_store)
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


def test_signup_with_a_short_password_returns_422_and_creates_no_user(monkeypatch, user_store):
    client, store = _client(monkeypatch, user_store)
    response = client.post(
        "/api/auth/signup",
        json={"email": "shorty@example.com", "password": "short"},  # < 8 chars
    )
    _clear()

    assert response.status_code == 422
    assert store.get_by_email("shorty@example.com") is None


def test_signup_with_an_already_registered_email_returns_409_and_no_duplicate(monkeypatch, user_store):
    client, store = _client(monkeypatch, user_store)
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


def test_signup_that_cannot_mint_a_verification_token_persists_no_user_and_stays_retryable(monkeypatch, user_store):
    """A token-mint failure must not strand a half-created, un-retryable
    account: no row is written, and the same email can be signed up again."""
    import assayingest.api.routes.auth as auth_route

    client, store = _client(monkeypatch, user_store)
    real_create_verification_token = auth_route.create_verification_token

    def _raise_token_failure(user_id: str) -> str:
        raise RuntimeError(
            "SESSION_SECRET is not set; cannot mint verification tokens."
        )

    monkeypatch.setattr(auth_route, "create_verification_token", _raise_token_failure)

    with pytest.raises(RuntimeError):
        client.post(
            "/api/auth/signup",
            json={"email": "retry@example.com", "password": "hunter2hunter"},
        )

    # Nothing was persisted by the failed attempt -- the email stays claimable.
    assert store.get_by_email("retry@example.com") is None

    # Restore the real function (not monkeypatch.undo(), which would also
    # unset the SESSION_SECRET `_client` set) and confirm the retry succeeds.
    monkeypatch.setattr(
        auth_route, "create_verification_token", real_create_verification_token
    )
    retry = client.post(
        "/api/auth/signup",
        json={"email": "retry@example.com", "password": "hunter2hunter"},
    )
    _clear()

    assert retry.status_code == 201
    retried_user = store.get_by_email("retry@example.com")
    assert retried_user is not None
    assert retried_user.is_verified is False


# --- login --------------------------------------------------------------------


def test_login_with_correct_credentials_sets_cookie_that_round_trips_to_me(monkeypatch, user_store):
    client, _store = _client(monkeypatch, user_store)
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


def test_login_with_a_wrong_password_returns_401_and_sets_no_cookie(monkeypatch, user_store):
    client, store = _client(monkeypatch, user_store)
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


def test_an_unverified_user_can_still_log_in(monkeypatch, user_store):
    """D-06-04: sign-in is allowed pre-verification; only governed actions
    are blocked until the email is verified."""
    client, store = _client(monkeypatch, user_store)
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


def test_verify_with_a_fresh_token_marks_the_user_verified(monkeypatch, caplog, user_store):
    client, store = _client(monkeypatch, user_store)
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


def test_verify_with_a_garbage_token_reports_expired_and_verifies_no_one(monkeypatch, user_store):
    client, store = _client(monkeypatch, user_store)
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


def test_logout_clears_the_session_cookie(monkeypatch, user_store):
    client, _store = _client(monkeypatch, user_store)
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


def test_config_reports_google_oauth_disabled_by_default(monkeypatch, user_store):
    client, _store = _client(monkeypatch, user_store)
    response = client.get("/api/auth/config")
    _clear()

    assert response.status_code == 200
    assert response.json() == {"google_oauth_enabled": False}
