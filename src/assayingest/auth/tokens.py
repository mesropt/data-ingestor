"""Email-verification token seam (D-06-04) -- the second module allowed to
import `itsdangerous`.

Same `URLSafeTimedSerializer` primitive as the session cookie but with a
DISTINCT `salt` and a short 24-hour `max_age`, so a verification link can never
be replayed as a session cookie and vice-versa (T-06-04, salt isolation).

The token is intentionally STATELESS/IDEMPOTENT: verification just flips
`is_verified` to True, which is a no-op the second time, so no `used_at` column
or server-side revocation list is needed (RESEARCH.md Pitfall 6). If a future
requirement makes verification non-idempotent (e.g. one-time-use with an audit
event on reuse), this is where a persisted per-token `used_at` would be added.
"""

from __future__ import annotations

import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_VERIFY_SALT = "data-ingestor-email-verify"
_VERIFY_MAX_AGE_SECONDS = 60 * 60 * 24  # 24 hours (D-06-04)


def _verify_serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        raise RuntimeError(
            "SESSION_SECRET is not set; cannot mint verification tokens. "
            "Set it in .env (see .env.example)."
        )
    return URLSafeTimedSerializer(secret, salt=_VERIFY_SALT)


def create_verification_token(user_id: str) -> str:
    """Sign a single verification token carrying `user_id` (raises if unset
    secret)."""
    return _verify_serializer().dumps({"user_id": user_id})


def read_verification_token(token: str) -> str | None:
    """Return the `user_id` a valid, unexpired verification token carries, or
    `None` on a tampered, expired, or wrong-salt token -- never raises on bad
    input."""
    try:
        data = _verify_serializer().loads(token, max_age=_VERIFY_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    return data.get("user_id")
