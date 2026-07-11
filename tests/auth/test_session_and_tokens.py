"""Session-cookie and email-verification token seams (D-06-01, D-06-04).

One `URLSafeTimedSerializer` primitive, two salted uses -- a leaked/expired
token minted for one use must never be replayable as the other (salt isolation),
and both fail loud (RuntimeError) when SESSION_SECRET is unset.
"""

from __future__ import annotations

import pytest

from assayingest.auth import session, tokens


def test_session_token_round_trips(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    token = session.create_session_token("u-1")
    assert session.read_session_token(token) == "u-1"


def test_mangled_session_token_returns_none(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    token = session.create_session_token("u-1")
    assert session.read_session_token(token + "tampered") is None


def test_session_token_signed_with_other_secret_returns_none(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "secret-a")
    token = session.create_session_token("u-1")
    monkeypatch.setenv("SESSION_SECRET", "secret-b")
    assert session.read_session_token(token) is None


def test_garbage_session_input_returns_none_not_raise(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    assert session.read_session_token("not-a-real-token") is None
    assert session.read_session_token("") is None


def test_verification_token_round_trips(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    token = tokens.create_verification_token("u-9")
    assert tokens.read_verification_token(token) == "u-9"


def test_session_and_verify_tokens_are_salt_isolated(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    session_token = session.create_session_token("u-1")
    verify_token = tokens.create_verification_token("u-1")
    # A session token is NOT a valid verification token and vice-versa.
    assert tokens.read_verification_token(session_token) is None
    assert session.read_session_token(verify_token) is None


def test_expired_verification_token_returns_none(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    token = tokens.create_verification_token("u-1")
    # Shrink the max-age so the just-minted token is already past it.
    monkeypatch.setattr(tokens, "_VERIFY_MAX_AGE_SECONDS", -1)
    assert tokens.read_verification_token(token) is None


def test_create_session_token_fails_loud_without_secret(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        session.create_session_token("u-1")


def test_create_verification_token_fails_loud_without_secret(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        tokens.create_verification_token("u-1")
