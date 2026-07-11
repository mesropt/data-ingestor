"""The email/password + config auth router (AUTH-01/03, D-06-04/06-07) --
signup, login, logout, verify, config, and a small `/me` session probe. The
Google OAuth routes (AUTH-02) are added to this same router in Task 2, gated
behind the off-by-default `DATA_INGESTOR_GOOGLE_OAUTH` flag.

Every credential check and cookie mint happens server-side (P1): a password is
verified only against the stored Argon2 hash (`auth.passwords`), the session
cookie is signed with `auth.session`'s itsdangerous serializer, and the
verification token is signed/read with `auth.tokens` -- this module never
re-implements any of those seams, it only wires them to HTTP.

The dev "email" for verification is the SERVER CONSOLE (D-06-04): signup logs
the full verification link (pointing at the SPA `/verify` landing, plan 06-03)
to the `assayingest.auth` logger. The password itself is NEVER logged.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ...auth.models import User
from ...auth.passwords import hash_password, verify_password
from ...auth.session import SESSION_COOKIE_NAME, create_session_token
from ...auth.store import UserStore
from ...auth.tokens import create_verification_token, read_verification_token
from ..deps import get_current_user, get_user_store
from ..wire import (
    AuthConfigOut,
    SignInIn,
    SignUpAcceptedOut,
    SignUpIn,
    UserOut,
)

#: The dev "email" channel (D-06-04): the verification link is logged here, to
#: the server console, instead of being sent to a real inbox.
logger = logging.getLogger("assayingest.auth")

#: The env flag gating the whole Google OAuth path (D-06-05, AUTH-02). Read at
#: request time (never import time) so a test can monkeypatch it per-case.
_GOOGLE_OAUTH_FLAG = "DATA_INGESTOR_GOOGLE_OAUTH"

_SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 14  # 14 days (D-06-01)

router = APIRouter(prefix="/api/auth")


def google_oauth_enabled() -> bool:
    """True iff the operator has explicitly enabled the Google OAuth path.
    Off by default so the app runs overnight with no provider secret."""
    return os.environ.get(_GOOGLE_OAUTH_FLAG) == "1"


def _set_session_cookie(response: Response, request: Request, user_id: str) -> None:
    """Set the HttpOnly login-session cookie. `secure` is derived from the LIVE
    request scheme (never hardcoded) so the cookie is `Secure` in production
    (https) yet still round-trips under FastAPI's http TestClient (RESEARCH.md
    Pitfall 3)."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(user_id),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=_SESSION_MAX_AGE_SECONDS,
        path="/",
    )


def _clear_session_cookie(response: Response, request: Request) -> None:
    """Expire the login-session cookie (logout) -- same attributes as the set
    so a compliant client reliably overwrites/drops it."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value="",
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=0,
        path="/",
    )


@router.post("/signup", status_code=201, response_model=SignUpAcceptedOut)
def signup(
    body: SignUpIn,
    request: Request,
    store: UserStore = Depends(get_user_store),
) -> SignUpAcceptedOut:
    """Create a password account (is_verified=False) and log the verification
    link to the server console (D-06-04). A duplicate email is a 409 naming the
    consequence, never an upsert over the existing account."""
    if store.get_by_email(body.email) is not None:
        raise HTTPException(
            status_code=409,
            detail="That email is already registered; sign in instead.",
        )

    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        password_hash=hash_password(body.password),
        is_verified=False,
        auth_provider="password",
        created_at=datetime.now(UTC).isoformat(),
    )
    store.save(user)

    token = create_verification_token(user.id)
    # Point the link at the SPA landing path (`/verify`, served by the frontend
    # catch-all, plan 06-03) -- opening it renders VerifyLanding, which then
    # calls GET /api/auth/verify. NEVER log the password.
    verify_url = f"{str(request.base_url).rstrip('/')}/verify?token={token}"
    logger.info("Email verification link for %s: %s", user.email, verify_url)

    return SignUpAcceptedOut(
        message="Account created. Check the server console for your verification link."
    )


@router.post("/login", response_model=UserOut)
def login(
    body: SignInIn,
    request: Request,
    response: Response,
    store: UserStore = Depends(get_user_store),
) -> UserOut:
    """Verify credentials against the stored Argon2 hash and set the session
    cookie. An unverified user may still log in (D-06-04); a wrong password (or
    an OAuth-only, password-less account) is a 401 that sets no cookie."""
    user = store.get_by_email(body.email)
    if user is None or user.password_hash is None or not verify_password(
        body.password, user.password_hash
    ):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    _set_session_cookie(response, request, user.id)
    return _to_user_out(user)


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, str]:
    """Clear the session cookie. Idempotent -- always 200, whether or not a
    cookie was present."""
    _clear_session_cookie(response, request)
    return {"status": "signed out"}


@router.get("/verify")
def verify_email(token: str, store: UserStore = Depends(get_user_store)) -> dict[str, str]:
    """Consume a verification token and flip the user to verified. Returns a
    distinguishable JSON status the SPA VerifyLanding branches on (plan 06-03):
    `verified` on success, `expired` on any invalid/expired/tampered token
    (idempotent -- verifying twice is a harmless no-op, RESEARCH.md Pitfall 6)."""
    user_id = read_verification_token(token)
    if user_id is None:
        return {"status": "expired"}
    store.mark_verified(user_id)
    return {"status": "verified"}


@router.get("/config", response_model=AuthConfigOut)
def config() -> AuthConfigOut:
    """The unauthenticated OAuth-flag surface the frontend reads (D-06-07)."""
    return AuthConfigOut(google_oauth_enabled=google_oauth_enabled())


@router.get("/me", response_model=UserOut)
def me(user: User | None = Depends(get_current_user)) -> UserOut:
    """The frontend session probe (D-06-07): the signed-in user, or 401 when
    signed out. Never a governed action -- a 401 here just means 'not signed
    in', not 'forbidden'."""
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return _to_user_out(user)


def _to_user_out(user: User) -> UserOut:
    """Domain `User` -> wire `UserOut` boundary translator -- drops
    `password_hash`/`created_at`, which never cross the wire."""
    return UserOut(
        id=user.id,
        email=user.email,
        is_verified=user.is_verified,
        auth_provider=user.auth_provider,
    )
