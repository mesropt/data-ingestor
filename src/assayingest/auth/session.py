"""Login-session cookie seam (D-06-01) -- one of the two modules allowed to
import `itsdangerous`.

A stateless signed cookie carrying `{"user_id": ...}`, minted on login/signup
and read on every request via `deps.get_current_user`. It fails loud
(RuntimeError) when `SESSION_SECRET` is unset rather than signing with an
insecure default (T-06-05, mirrors the `MissingCredentialsError` convention).
The `salt` here is distinct from the verification-token salt (`tokens.py`) so a
session cookie can never be replayed as a verification token (T-06-04).
"""

from __future__ import annotations

import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

#: The HttpOnly session cookie name the API sets and `deps` reads.
SESSION_COOKIE_NAME = "di_session"

_SESSION_SALT = "data-ingestor-session"
_SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 14  # 14 days (D-06-01)


def _serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        # Fail loud at first use, not silently with an insecure default --
        # the error names the consequence (CLAUDE.md convention).
        raise RuntimeError(
            "SESSION_SECRET is not set; cannot sign session cookies. "
            "Set it in .env (see .env.example)."
        )
    return URLSafeTimedSerializer(secret, salt=_SESSION_SALT)


def create_session_token(user_id: str) -> str:
    """Sign a session cookie value carrying `user_id` (raises if unset secret)."""
    return _serializer().dumps({"user_id": user_id})


def read_session_token(token: str) -> str | None:
    """Return the `user_id` a valid, unexpired token carries, or `None` on a
    tampered, expired, or otherwise unreadable token -- never raises so
    `get_current_user` can depend on it (a missing secret still raises, since
    that is a server misconfiguration, not attacker input)."""
    try:
        data = _serializer().loads(token, max_age=_SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    return data.get("user_id")
