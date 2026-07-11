# Phase 6: Auth & Attribution - Research

**Researched:** 2026-07-11
**Domain:** Session-cookie authentication, password hashing, feature-flagged OAuth, and identity threading in a FastAPI + React app
**Confidence:** MEDIUM (core session/hashing pattern verified against multiple independent sources incl. official docs; OAuth wiring and a few library-version specifics are WebSearch-only, no Context7/MCP available this session — see Assumptions Log)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-06-01 — Session mechanism: signed HttpOnly cookie.** Use a stateless signed session cookie (`HttpOnly`, `SameSite=Lax`, `Secure` when not localhost) carrying the user id, signed server-side (itsdangerous / Starlette `SessionMiddleware`, or a short JWT in the cookie — planner's exact lib call). Rationale: no server-side session table to manage, works same-origin with the Phase 4 single-process deployment, and the Phase 4 dev CORS already sets `allow_credentials=True`. A server-side session table is acceptable if the planner prefers it, but the cookie MUST stay `HttpOnly`.
- **D-06-02 — User store extends the existing local SQLite behind the DI seam.** Add a `users` table to the same SQLite database the profile/field-set stores use, exposed through a new repository (`UserStore`) injected via a `deps.py` `get_user_store()` function — mirroring `get_profile_store()` / `get_field_set_store()`. Tests override it with a tmp-path store; no test touches the real demo DB. Clean-Architecture boundary: a pure-Python `User` domain model, wire models stay at the API edge.
- **D-06-03 — Password hashing with a modern KDF.** Hash passwords with bcrypt or argon2 (via `passlib` or `argon2-cffi` / `bcrypt` — planner picks one and adds the dep). Never store or log plaintext. Basic strength rule: minimum length (e.g. ≥ 8); do not over-engineer policy (ASVS L1).
- **D-06-04 — Email verification: console-printed link (dev fallback).** On sign-up, mint a single-use, expiring verification token; print the full verification URL to the server console (via the app logger / stdout) instead of emailing it. A `GET/POST /api/auth/verify` endpoint consumes the token and marks the user verified. Decision on whether an unverified user may sign in but not perform governed actions vs cannot sign in at all: **allow sign-in but block governed actions until verified** — planner may flip if cleaner, but AUTH-03's console-link completion must be demonstrable.
- **D-06-05 — Google OAuth behind an off-by-default feature flag.** Implement the OAuth authorization-code route(s) (`/api/auth/google/login` → redirect, `/api/auth/google/callback`) using a standard lib (Authlib preferred). Gate the whole path behind an env flag (e.g. `DATA_INGESTOR_GOOGLE_OAUTH=1`, default off) reading placeholder `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` from env. When the flag is off: the routes return a clear `501/404` and the frontend hides or disables the "Sign in with Google" button. Add the placeholder vars to `.env.example`. No live secret is committed or required.
- **D-06-06 — The gate is a reusable dependency; identity threads into confirm.** Provide `require_user` (FastAPI `Depends`) returning the authenticated `User`; apply it now to `/api/confirm` (AUTH-01 server-side). Thread the user's identity (email/id) into the confirm service call so it is available to stamp provenance — Phase 07 consumes it for ALIAS-03/04. Phase 06's job is to make identity present and recorded at the confirm boundary, not to build the crosswalk. A lightweight record (e.g. `confirmed_by` on whatever the confirm path persists, or simply passing it through to be returned) satisfies AUTH-04; do not over-build.
- **D-06-07 — Frontend auth surface.** Add: a small auth store/context, a Sign up and Sign in view, an "check the server console for your verification link" notice after sign-up, the current-signed-in-user indicator + sign-out in the AppShell, and a Google button that only shows when the backend reports the OAuth flag is on (expose flag state via a tiny `/api/auth/config` or the existing config surface). The Confirm & Save action is disabled/redirects to sign-in when signed out (mirrors the server gate). Keep the existing shadcn / `data-theme` dark aesthetic.

### Claude's Discretion

- Exact session lib (Starlette `SessionMiddleware` vs itsdangerous vs JWT-in-cookie) and cookie max-age.
- Exact users table columns beyond the essentials (id, email, password_hash, is_verified, created_at, auth_provider).
- Whether verification token lives in the users table or its own table.
- Route module layout under `api/routes/auth.py` (likely one new router) and wire-model shapes.
- React auth state approach (context + hook vs a store file like the existing `state/` modules) and routing for the auth views.
- Whether to add a minimal password reset — only if trivial; not required.

### Deferred Ideas (OUT OF SCOPE)

- Organizations / multi-tenancy (FUTURE).
- Roles/permissions beyond "signed in" (FUTURE).
- Real email delivery.
- Live Google OAuth credentials.
- Password reset flow (nice-to-have, not required by AUTH-01..04 — defer unless trivial).
- The Schema CRUD endpoints themselves (Phase 07 builds them and applies this phase's gate).

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-01 | A user can create an account and sign in; creating/editing a Schema or confirming a mapping requires being signed in. | `require_user` FastAPI dependency (Architecture Patterns §1), applied to `/api/confirm`; sign-up/sign-in routes + password hashing (Standard Stack); frontend `ConfirmGate` mirror (already specified in UI-SPEC, this research covers the wiring only) |
| AUTH-02 | A user can sign in with Google OAuth (feature-flagged, dev placeholders, off by default). | Authlib authorization-code pattern (Architecture Patterns §3), `/api/auth/config` flag surface, `.env.example` placeholders |
| AUTH-03 | A user can verify their email; dev build prints the link to console instead of emailing it. | itsdangerous `URLSafeTimedSerializer` single-use expiring token (Architecture Patterns §2), `GET /api/auth/verify` endpoint, logger-based console print (Code Examples) |
| AUTH-04 | Every manual mapping edit/confirmation is attributed to the signed-in user (identity recorded for alias provenance). | Minimal seam: `confirmed_by` threaded through `service.confirm()` → `build_manifest()` (Architecture Patterns §6) |

</phase_requirements>

## Summary

This phase adds a conventional cookie-session auth layer on top of an already-shipped, dependency-injection-heavy FastAPI app. The codebase's own idioms (a `ProfileStore`/`FieldSetTemplateStore` ABC + one `Sqlite*` implementation behind a `deps.py` factory function, `Depends()`-based DI everywhere, frozen-dataclass domain models, wire models isolated to `api/wire.py`) dictate almost the entire shape of the solution: a `UserStore` ABC + `SqliteUserStore` in `learning/` (or a new `auth/` package — recommended, see below), a `get_user_store()` factory in `deps.py`, and a `require_user`/`require_verified_user` dependency next to it. No new architectural pattern needs to be invented.

**Recommended stack:** `itsdangerous` (`URLSafeTimedSerializer`) for both the session cookie and the email-verification token — used directly, not via Starlette's `SessionMiddleware` — because a single explicit `Depends()`-based reader/writer pair fits this codebase's "no global middleware except CORS" convention far better than a request-scoped `request.session` dict. `pwdlib[argon2]` for password hashing (Argon2, with bcrypt kept available for future hash migration) instead of `passlib`, which is unmaintained and breaks on Python 3.13. `Authlib` for the flagged Google OAuth authorization-code flow, following its official FastAPI/Starlette integration exactly, including the fact that Authlib's OAuth client itself needs Starlette's `SessionMiddleware` (only) to hold the OAuth `state`/`nonce` across the redirect round trip — this is the one place `SessionMiddleware` is actually the standard tool, and it is fully independent of (and does not replace) the app's own itsdangerous-signed login-session cookie.

**Primary recommendation:** Add `itsdangerous`, `pwdlib[argon2]`, and `authlib` as new dependencies; build a `src/assayingest/auth/` package (`models.py` domain `User`, `store.py` ABC, `sqlite_store.py` impl, `session.py` cookie sign/verify, `passwords.py` hash/verify, `tokens.py` verification-token sign/verify) plus `api/routes/auth.py` (sign-up, sign-in, sign-out, verify, google login/callback, config); wire `get_user_store()`, `get_current_user`, `require_user`, `require_verified_user` into `deps.py`; gate `/api/confirm` with `require_verified_user` and thread `confirmed_by=user.email` into `service.confirm()` → the manifest.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Sign-up / sign-in / sign-out (credential check, cookie mint) | API / Backend | — | Password verification and cookie signing must never touch the browser; matches P1 (server-side gate) |
| Session validation (`require_user`) | API / Backend | — | The one gate that must be un-bypassable; enforced per-request via `Depends()`, never trusted from a client-sent flag |
| Password hashing/verification | API / Backend | Database / Storage (stores only the hash) | Hashing is pure compute at the API tier; only the resulting hash is persisted |
| Email verification token mint + consume | API / Backend | Database / Storage (persists token or `is_verified` flag) | Token generation/validation is server logic; the "email" itself is simulated by printing to the server console (stdout), not a separate tier |
| Google OAuth redirect + callback | API / Backend | Browser (redirect target) | Authlib drives the authorization-code exchange server-side; the browser only ever follows redirects, never handles the client secret |
| `/api/auth/config` (OAuth-flag surface) | API / Backend | Browser (conditionally renders Google button) | A tiny read-only capability flag; backend is the single source of truth for whether OAuth is enabled |
| Signed-in identity chip, sign-out button, gated Confirm button | Browser / Client | — | UX mirror only (already specified in `06-UI-SPEC.md`); never the actual gate (P1) |
| `confirmed_by` attribution stamp | API / Backend | Database / Storage (written into the manifest / future alias row) | The identity must be captured at the exact moment `service.confirm()` runs, server-side, from the `require_verified_user`-resolved `User`, never from a client-supplied field |
| `users` table (SQLite) | Database / Storage | — | Same local SQLite file as `profiles`/`field_set_templates` (D-06-02); no network DB (P2) |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `itsdangerous` | 2.2.0 [VERIFIED: uv resolver against PyPI] | Sign/verify the session cookie payload and the email-verification token (`URLSafeTimedSerializer`) | The Flask/Pallets-ecosystem standard for exactly this ("itsdangerous" was built for signed cookie tokens); already the library Starlette's own `SessionMiddleware` uses internally, so it's a zero-surprise dependency for a FastAPI/Starlette app [CITED: WebSearch — multiple FastAPI session tutorials converge on it] |
| `pwdlib[argon2]` | 0.3.0 [VERIFIED: uv resolver against PyPI] | Hash and verify passwords (Argon2id via `argon2-cffi` backend) | Modern, actively maintained; used internally by `fastapi-users` as its default hasher; explicitly created because `passlib` (the older de-facto standard) is unmaintained (last release ~3 years) and its `bcrypt` backend detection breaks against `bcrypt>=4.1`/`5.0` (`__about__` attribute removed) [CITED: github.com/frankie567/pwdlib, fastapi-users docs — MEDIUM confidence, WebSearch cross-checked against official project docs] |
| `authlib` | 1.7.2 [VERIFIED: uv resolver against PyPI] | Google OAuth 2.0 authorization-code flow client (behind the feature flag) | The standard OAuth/OIDC client library recommended directly by FastAPI's own ecosystem docs and Authlib's own official FastAPI/Starlette integration guide (`docs.authlib.org/en/latest/client/{starlette,fastapi}.html`) — this is D-06-05's explicit "Authlib preferred" [CITED: docs.authlib.org] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `argon2-cffi` | 25.1.0 [VERIFIED: uv resolver] | Argon2 backend `pwdlib[argon2]` pulls in transitively | Never imported directly — `pwdlib` is the only import site (keeps a single hashing seam, mirrors the "one place imports sqlite3" convention already in this codebase) |
| `starlette.middleware.sessions.SessionMiddleware` | ships with `starlette` 1.3.1 (already a transitive dep via `fastapi`) | Holds Authlib's OAuth `state`/`nonce` across the Google redirect round trip **only** | Add this middleware **only when** `DATA_INGESTOR_GOOGLE_OAUTH=1` (register it conditionally in `app.py`, mirroring the existing `if os.environ.get("ASSAYINGEST_DEV_CORS") == "1":` conditional-middleware pattern) — it is unrelated to and must not be confused with the app's own itsdangerous-signed login-session cookie |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Direct `itsdangerous` reader/writer | Starlette's built-in `SessionMiddleware` for the login session too | `SessionMiddleware` auto-manages a whole `request.session` dict and installs global middleware that touches every request; a direct `URLSafeTimedSerializer` call inside a `Depends()` function fits this project's existing "everything is an explicit DI seam, no global middleware except CORS" convention far better, and keeps the session payload to exactly `{"user_id": ..., "iat": ...}` — nothing implicit |
| `pwdlib[argon2]` | `bcrypt` directly, or `passlib[bcrypt]` | `passlib` is unmaintained and Python-3.13-broken; raw `bcrypt` works but has no upgrade/legacy-hash migration path and the 72-byte silent-truncation gotcha (see Common Pitfalls); `pwdlib` wraps `argon2-cffi` (no such length ceiling) and ships a `verify_and_update()` seam for future algorithm migration at near-zero extra code |
| `Authlib` | Hand-rolled `httpx` calls to Google's OAuth endpoints | Hand-rolling authorization-code + PKCE/state/nonce handling is exactly the kind of "deceptively complex, get security-critical details wrong" problem the Don't-Hand-Roll table below calls out — Authlib is a maintained, security-audited implementation |
| Cookie-based session | JWT-in-cookie (stateless, no DB round-trip) | Explicitly allowed by D-06-01 ("or a short JWT in the cookie") but not recommended here: a JWT needs its own library (`pyjwt`, resolves to 2.13.0) for no material benefit over `itsdangerous` at this scale (single-process demo, no cross-service token verification need) — `itsdangerous`'s `URLSafeTimedSerializer` already gives signing + built-in expiry (`max_age`) with fewer moving parts |

**Installation:**
```bash
uv add itsdangerous "pwdlib[argon2]" authlib
```

**Version verification:** Verified via `uv pip install --dry-run itsdangerous "pwdlib[argon2]" authlib` against the live PyPI index on 2026-07-11 (this session), which resolved: `itsdangerous==2.2.0`, `pwdlib==0.3.0`, `argon2-cffi==25.1.0`, `argon2-cffi-bindings==25.1.0`, `authlib==1.7.2`. `starlette` is already pinned at `1.3.1` in `uv.lock` (a transitive dependency of `fastapi==0.139.0`) and does **not** currently pull in `itsdangerous` transitively in this lockfile — it must be added as an explicit direct dependency regardless of which session approach is chosen.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `itsdangerous` | PyPI | published 2024-04-16 (Pallets project, existed for over a decade prior; this is a routine release, not the project's origin) | unknown (tool has no PyPI download-stats source) | github.com/pallets/itsdangerous | SUS (`unknown-downloads`) | Flagged — planner must add `checkpoint:human-verify`, but note below |
| `pwdlib` | PyPI | published 2025-10-25 | unknown | github.com/frankie567/pwdlib | SUS (`unknown-downloads`) | Flagged — planner must add `checkpoint:human-verify`, but note below |
| `argon2-cffi` | PyPI | published 2025-06-03 | unknown | none returned by the legitimacy tool (well-known maintainer: Hynek Schlawack) | SUS (`unknown-downloads`, `no-repository`) | Flagged — planner must add `checkpoint:human-verify`, but note below |
| `authlib` | PyPI | published 2026-05-06 | unknown | github.com/authlib/authlib | SUS (`unknown-downloads`) | Flagged — planner must add `checkpoint:human-verify`, but note below |
| `bcrypt` (transitive, via `pwdlib[argon2]`'s ecosystem, NOT installed directly — see Standard Stack) | PyPI | published 2025-09-25 | unknown | none returned by the legitimacy tool (well-known maintainer: pyca org) | SUS (`unknown-downloads`, `no-repository`) | Not installed by this phase's recommendation — informational only |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `itsdangerous`, `pwdlib`, `argon2-cffi`, `authlib` — **all four flags are driven entirely by the `unknown-downloads` signal**, i.e. the legitimacy tool has no PyPI download-count data source configured for this ecosystem, not by any actual community-distrust signal. Cross-checked independently this session: `itsdangerous` is a Pallets-org project (same org as Flask/Jinja2) and is the library Starlette's own `SessionMiddleware` uses internally [CITED: WebSearch, multiple sources]; `authlib` and `pwdlib` both resolved to their real GitHub repos (`authlib/authlib`, `frankie567/pwdlib`) with `frankie567` being the maintainer of `fastapi-users` [CITED: github.com/frankie567/pwdlib]; `argon2-cffi` is maintained by Hynek Schlawack, a well-known CPython security-adjacent maintainer, though the tool did not surface a repo URL for it. **None of this cross-checking substitutes for the required gate** — per protocol, the planner MUST still insert a `checkpoint:human-verify` task before each of these four installs, since the automated verdict is SUS regardless of this research's own corroboration.

## Architecture Patterns

### System Architecture Diagram

```
Browser (React)                    FastAPI (api/app.py)                  SQLite (.assayingest/*.db)
────────────────                   ─────────────────────                 ──────────────────────────
POST /api/auth/signup ───────────► routes/auth.py: signup()
  {email, password}                  │  pwdlib.hash(password)
                                      │  UserStore.save(User) ─────────► users table (INSERT)
                                      │  mint verification token
                                      │  (itsdangerous URLSafeTimedSerializer)
                                      │  logger.info(verify_url)  ──────► [printed to server console]
                                      ◄─ 201 {"verify_hint": "check console"}

GET  /api/auth/verify?token=… ────► routes/auth.py: verify()
                                      │  itsdangerous.loads(token, max_age=…)
                                      │  UserStore.mark_verified(user_id) ─► users table (UPDATE)
                                      ◄─ 200 / redirect to Sign-In-landing

POST /api/auth/login ─────────────► routes/auth.py: login()
  {email, password}                   │  UserStore.get_by_email(email)
                                      │  pwdlib.verify(password, hash)
                                      │  session.create_session_token(user.id)
                                      ◄─ 200, Set-Cookie: di_session=<signed>; HttpOnly; SameSite=Lax

GET  /api/auth/config ─────────────► routes/auth.py: config()
                                      ◄─ 200 {"google_oauth_enabled": bool}
  (conditionally render Google btn)

fetch(..., credentials:'include') ─► deps.py: get_current_user()
  (every subsequent request,          │  Cookie("di_session") → session.read_session_token()
   including /api/confirm)            │  UserStore.get(user_id)
                                      ▼
                          deps.py: require_verified_user()
                              │  raises 401 if no user; 403 if unverified
                              ▼
POST /api/confirm ─────────────────► routes/confirm.py: confirm(user=Depends(require_verified_user))
  {upload_token, field_mappings}       │  service.confirm(..., confirmed_by=user.email)
                                      │  build_manifest(..., confirmed_by=user.email)
                                      ◄─ 200 {"manifest": {..., "confirmed_by": "user@example.com"}}

[flag ON only]
GET /api/auth/google/login ────────► routes/auth.py: google_login()
                                      │  oauth.google.authorize_redirect(request, redirect_uri)
                                      ◄─ 302 → accounts.google.com
GET /api/auth/google/callback ─────► routes/auth.py: google_callback()
                                      │  oauth.google.authorize_access_token(request)
                                      │  UserStore.get_or_create_by_email(userinfo.email)
                                      │  session.create_session_token(user.id)
                                      ◄─ 302 → frontend, Set-Cookie: di_session=…
```

### Recommended Project Structure
```
src/assayingest/
├── auth/                       # NEW package -- mirrors learning/'s store+impl split
│   ├── __init__.py
│   ├── models.py                # User (frozen dataclass, pure Python)
│   ├── store.py                 # UserStore ABC (mirrors learning/store.py)
│   ├── sqlite_store.py          # SqliteUserStore (mirrors learning/sqlite_store.py)
│   ├── passwords.py              # hash_password()/verify_password() -- pwdlib seam
│   ├── session.py                # create_session_token()/read_session_token() -- itsdangerous seam
│   └── tokens.py                 # create_verification_token()/read_verification_token()
├── api/
│   ├── deps.py                   # + get_user_store(), get_current_user(), require_user(), require_verified_user()
│   ├── wire.py                   # + SignUpIn, SignInIn, AuthConfigOut, UserOut, etc.
│   └── routes/
│       ├── auth.py               # NEW router: signup, login, logout, verify, google/login, google/callback, config
│       └── confirm.py            # MODIFIED: + user=Depends(require_verified_user), thread confirmed_by
frontend/src/
├── state/
│   └── auth.ts                   # NEW -- mirrors upload.ts's reducer idiom (or a lightweight context, planner's call)
├── lib/
│   └── api.ts                    # MODIFIED: credentials:'include' on request(); + auth call wrappers
└── components/
    ├── SignUpScreen.tsx           # NEW (per 06-UI-SPEC.md)
    ├── SignInScreen.tsx           # NEW
    ├── VerifyLanding.tsx          # NEW
    ├── GoogleSignInButton.tsx     # NEW, conditional on /api/auth/config
    ├── SignedInIndicator.tsx      # NEW -- AppShell trailing group
    ├── AppShell.tsx               # MODIFIED: + SignedInIndicator
    └── ConfirmGate.tsx            # MODIFIED: + auth-gate priority tier (per 06-UI-SPEC.md)
```

### Pattern 1: `require_user` / `require_verified_user` as layered FastAPI dependencies

**What:** Two small, composable `Depends()` functions — `get_current_user` (returns `User | None`, never raises) and `require_user` (raises `401` if `None`) — with a third, `require_verified_user`, layered on top for D-06-04's "sign-in allowed, governed actions blocked until verified" rule.

**When to use:** Any endpoint that needs "signed in" (e.g. a future `/api/schemas` POST in Phase 07) uses `require_user`; any endpoint that needs "signed in AND verified" (this phase's `/api/confirm`) uses `require_verified_user`.

**Example:**
```python
# Source: pattern synthesized from FastAPI's own dependency-injection docs
# (fastapi.tiangolo.com/tutorial/dependencies/) + this codebase's existing
# deps.py idiom (get_profile_store/get_field_set_store) -- [CITED: FastAPI docs, ASSUMED wiring specifics]

# src/assayingest/api/deps.py (additions)
from fastapi import Cookie, Depends, HTTPException

from ..auth.models import User
from ..auth.session import read_session_token
from ..auth.sqlite_store import SqliteUserStore
from ..auth.store import UserStore

_SESSION_COOKIE_NAME = "di_session"


def get_user_store() -> UserStore:
    """Default: the same local SQLite path the profile/field-set stores use
    (D-06-02). Tests override this with a tmp-path store."""
    return SqliteUserStore()


def get_current_user(
    di_session: str | None = Cookie(default=None, alias=_SESSION_COOKIE_NAME),
    store: UserStore = Depends(get_user_store),
) -> User | None:
    """Never raises -- a caller that only needs to KNOW who's signed in
    (e.g. /api/auth/config or a UI-only affordance) can depend on this
    directly. Returns None on a missing, expired, or tampered cookie."""
    if di_session is None:
        return None
    user_id = read_session_token(di_session)
    if user_id is None:
        return None
    return store.get(user_id)


def require_user(user: User | None = Depends(get_current_user)) -> User:
    """The P1 server-side gate (AUTH-01): raises 401 for any signed-out
    request to a governed endpoint, regardless of what the client renders."""
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to perform this action.")
    return user


def require_verified_user(user: User = Depends(require_user)) -> User:
    """D-06-04: signed-in but unverified users may reach this far (they ARE
    authenticated) but are still forbidden from a governed action -- 403,
    not 401, since re-authenticating would not fix it."""
    if not user.is_verified:
        raise HTTPException(
            status_code=403,
            detail="Verify your email to perform this action.",
        )
    return user
```

### Pattern 2: itsdangerous-signed session cookie (login) and verification token (email)

**What:** One `itsdangerous.URLSafeTimedSerializer`, two salted uses — a login-session payload (`{"user_id": ...}`) with a long `max_age` (e.g. 14 days) and a verification-token payload (`{"user_id": ...}`) with a short `max_age` (e.g. 24 hours), distinguished by `salt=` so a leaked/expired token from one use can never be replayed as the other.

**When to use:** Session cookie: set on successful login/signup/OAuth callback, read on every request via `get_current_user`. Verification token: minted on signup, consumed exactly once by `GET /api/auth/verify`.

**Example:**
```python
# Source: itsdangerous official docs (itsdangerous.palletsprojects.com) pattern
# for URLSafeTimedSerializer.dumps()/.loads(max_age=...); FastAPI cookie-setting
# via Response.set_cookie is FastAPI's own documented API
# (fastapi.tiangolo.com/advanced/response-cookies/).
# [CITED: itsdangerous docs, FastAPI docs — MEDIUM confidence, WebSearch this session]

# src/assayingest/auth/session.py
from __future__ import annotations

import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE_NAME = "di_session"
_SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 14  # 14 days


def _serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        # Fails loudly at first use, not silently with an insecure default --
        # matches CLAUDE.md's "error names the consequence" convention.
        raise RuntimeError(
            "SESSION_SECRET is not set; cannot sign session cookies. "
            "Set it in .env (see .env.example)."
        )
    return URLSafeTimedSerializer(secret, salt="data-ingestor-session")


def create_session_token(user_id: str) -> str:
    return _serializer().dumps({"user_id": user_id})


def read_session_token(token: str) -> str | None:
    try:
        data = _serializer().loads(token, max_age=_SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")


# src/assayingest/auth/tokens.py -- same serializer class, different salt/max_age
_VERIFY_MAX_AGE_SECONDS = 60 * 60 * 24  # 24 hours


def _verify_serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        raise RuntimeError("SESSION_SECRET is not set; cannot mint verification tokens.")
    return URLSafeTimedSerializer(secret, salt="data-ingestor-email-verify")


def create_verification_token(user_id: str) -> str:
    return _verify_serializer().dumps({"user_id": user_id})


def read_verification_token(token: str) -> str | None:
    try:
        data = _verify_serializer().loads(token, max_age=_VERIFY_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")
```

```python
# src/assayingest/api/routes/auth.py -- setting the cookie, deriving `secure`
# from the LIVE request scheme rather than a hardcoded flag (see Common
# Pitfalls #3 -- this also makes the cookie correctly testable with
# FastAPI's TestClient, which defaults to http://testserver).
from fastapi import APIRouter, Request, Response

from ...auth.session import SESSION_COOKIE_NAME, create_session_token

router = APIRouter(prefix="/api/auth")


def _set_session_cookie(response: Response, request: Request, user_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(user_id),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=60 * 60 * 24 * 14,
        path="/",
    )
```

### Pattern 3: Authlib feature-flagged Google OAuth (authorization-code flow)

**What:** Register a Google OAuth client via Authlib's `OAuth` registry using Google's OIDC discovery document; a `/login` route redirects, a `/callback` route exchanges the code. The entire router (or each individual route body) checks the feature flag first and short-circuits with `501` when off — matching D-06-05's "routes return a clear 501/404" requirement.

**When to use:** Only when `DATA_INGESTOR_GOOGLE_OAUTH=1` is set. Off by default; this is the overnight-runnable path (AUTH-02, no live secret required).

**Example:**
```python
# Source: Authlib's official FastAPI/Starlette OAuth client integration guide
# (docs.authlib.org/en/latest/client/{starlette,fastapi}.html) --
# [CITED: docs.authlib.org, MEDIUM confidence -- WebSearch this session,
# official docs URL surfaced directly in results, no MCP fetch available
# to pull the literal doc page this session]

import os

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request

_GOOGLE_OAUTH_FLAG = "DATA_INGESTOR_GOOGLE_OAUTH"


def google_oauth_enabled() -> bool:
    return os.environ.get(_GOOGLE_OAUTH_FLAG) == "1"


def _oauth_client() -> OAuth:
    oauth = OAuth()
    oauth.register(
        name="google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth


router = APIRouter(prefix="/api/auth/google")


@router.get("/login")
async def google_login(request: Request):
    if not google_oauth_enabled():
        raise HTTPException(status_code=501, detail="Google sign-in is not enabled on this server.")
    oauth = _oauth_client()
    redirect_uri = request.url_for("google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def google_callback(request: Request):
    if not google_oauth_enabled():
        raise HTTPException(status_code=501, detail="Google sign-in is not enabled on this server.")
    oauth = _oauth_client()
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    # ... get_or_create_by_email(userinfo["email"]), then set the session cookie
```

**IMPORTANT:** Authlib's `authorize_redirect`/`authorize_access_token` calls require `request.session` to exist — i.e. Starlette's `SessionMiddleware` **must** be registered on the app for this to work, but **only** to hold the OAuth `state`/`nonce`, and only when the flag is on:

```python
# src/assayingest/api/app.py -- mirrors the existing conditional-middleware
# pattern already used for ASSAYINGEST_DEV_CORS.
if os.environ.get("DATA_INGESTOR_GOOGLE_OAUTH") == "1":
    from starlette.middleware.sessions import SessionMiddleware

    app.add_middleware(SessionMiddleware, secret_key=os.environ["SESSION_SECRET"])
```

### Pattern 4: `/api/auth/config` — the flag surface the frontend reads

**What:** A tiny unauthenticated `GET` endpoint returning `{"google_oauth_enabled": bool}` — the single source of truth D-06-07 asks for so the Google button only renders when the backend is actually configured for it.

**Example:**
```python
# src/assayingest/api/routes/auth.py
from pydantic import BaseModel


class AuthConfigOut(BaseModel):
    google_oauth_enabled: bool


@router.get("/config", response_model=AuthConfigOut)
def auth_config() -> AuthConfigOut:
    return AuthConfigOut(google_oauth_enabled=google_oauth_enabled())
```

### Pattern 5: Threading `confirmed_by` into `service.confirm()` (AUTH-04, minimal seam)

**What:** Add one optional keyword-only parameter to `service.confirm()` and `export/writers.py::build_manifest()`, defaulting to `None` so every existing CLI call site (which has no authenticated user) is unaffected.

**Example:**
```python
# src/assayingest/service.py -- confirm() signature, additive only
def confirm(
    table: RawTable,
    edited_mappings: list[FieldMapping],
    field_set: FieldSet,
    *,
    save_profile: bool = False,
    strictness: str = "strict",
    store: ProfileStore | None = None,
    hint: StructuralHint | None = None,
    provenance: str = "fresh-claude",
    confirmed_by: str | None = None,   # NEW -- AUTH-04
) -> ConfirmResult:
    ...
    manifest = build_manifest(
        field_set, table.headers, proposal,
        provenance=provenance, strictness=strictness,
        confirmed_by=confirmed_by,      # NEW
    )
    ...

# src/assayingest/export/writers.py -- build_manifest(), additive only
def build_manifest(
    field_set: FieldSet, headers: list[str], proposal: MappingProposal,
    *, provenance: str, strictness: str, confirmed_by: str | None = None,
) -> dict:
    return {
        ...,
        "confirmed_by": confirmed_by,   # NEW -- None on the CLI path, the
                                         # user's email on the API path
    }

# src/assayingest/api/routes/confirm.py -- route body, additive only
@router.post("/api/confirm")
def confirm(
    body: ConfirmRequest,
    store=Depends(get_profile_store),
    user: User = Depends(require_verified_user),   # NEW -- AUTH-01/04 gate
) -> ConfirmResponse:
    ...
    result = service.confirm(
        entry.table, edited_mappings, field_set,
        save_profile=body.save_profile, store=store, provenance=provenance,
        confirmed_by=user.email,                    # NEW -- AUTH-04
    )
    ...
```

This is deliberately the *entire* AUTH-04 seam for this phase — the manifest dict already flows to `export.py`'s `manifest.json` and to `ConfirmResponse.manifest`, so `confirmed_by` is now present and recorded at both persistence points without building any crosswalk/alias machinery (that is Phase 07's job, per D-06-06).

### Anti-Patterns to Avoid

- **Using Starlette's `SessionMiddleware` for the app's own login session:** it is the right tool for Authlib's transient OAuth state/nonce (Pattern 3) but the wrong tool for the durable login session — it installs global request/response middleware and stores an entire mutable dict, when this app only ever needs one immutable `user_id` claim. Keep the two uses (OAuth handshake state vs. login session) on two separate mechanisms so a reader is never confused about which "session" a given piece of code means.
- **Hardcoding `secure=True`/`secure=False` on the cookie:** breaks either production (if `False`) or every `TestClient`-based test (if `True`, see Common Pitfalls #3). Derive it from `request.url.scheme == "https"` at the point the cookie is set.
- **Trusting `is_verified` from anywhere but the freshly-loaded `User` row:** never accept a client-sent "I'm verified" flag; `require_verified_user` must re-read the DB-backed `User.is_verified` on every request (mirrors this codebase's existing "never trust a client-claimed ready flag" P1 discipline in `service.confirm`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Password hashing | A custom PBKDF2/salt-rolling scheme, or raw `hashlib.sha256(password)` | `pwdlib[argon2]` | Argon2's parameters (memory cost, iterations, parallelism) are themselves a security-critical tuning problem; a wrapper library that ships good defaults and a verify-and-upgrade path is the entire point of not hand-rolling this |
| Session token signing | A hand-rolled HMAC-over-JSON scheme | `itsdangerous.URLSafeTimedSerializer` | Correct constant-time comparison, timestamp-based expiry, and URL-safe encoding are all easy to get subtly wrong; `itsdangerous` is a 10+ year old, widely-audited library built for exactly this |
| OAuth authorization-code + PKCE/state/nonce handling | Manual `httpx` calls to Google's `/o/oauth2/v2/auth` and `/token` endpoints | `Authlib`'s `OAuth` registry + `authorize_redirect`/`authorize_access_token` | CSRF-state and OIDC-nonce validation are the most common source of real-world OAuth vulnerabilities; Authlib handles both transparently |
| Single-use expiring tokens (email verification) | A hand-rolled UUID + manual expiry-timestamp column and a custom comparison | `itsdangerous.URLSafeTimedSerializer` with a distinct `salt` and `max_age` | Reuses the exact same audited primitive as the session cookie; no second signing scheme to maintain, and no separate DB column needed to track expiry (the timestamp is embedded in the signed payload itself) |

**Key insight:** Every "Don't Hand-Roll" item above is a security-critical primitive with well-known failure modes (timing attacks, replay, insufficient entropy, CSRF). This project's own existing convention — one narrow seam per infrastructure concern (`sqlite3` only in `learning/sqlite_store.py`) — extends naturally to auth: `itsdangerous` only in `auth/session.py`/`auth/tokens.py`, `pwdlib` only in `auth/passwords.py`, `authlib` only in `api/routes/auth.py`'s Google-specific functions.

## Common Pitfalls

### Pitfall 1: `passlib` + modern `bcrypt` breakage
**What goes wrong:** If a future contributor reaches for the "traditional" `passlib[bcrypt]` combo instead of this research's `pwdlib[argon2]` recommendation, `passlib`'s bcrypt backend detection fails against `bcrypt>=4.1`/`5.0` (the `__about__` attribute was removed), producing a misleading "password cannot be longer than 72 bytes" error even for a 10-character password.
**Why it happens:** `passlib` is unmaintained (no release addressing this) and its backend-detection code inspects an attribute `bcrypt` no longer exports.
**How to avoid:** Do not add `passlib` to this project at all; use `pwdlib[argon2]` per the Standard Stack recommendation.
**Warning signs:** A `ValueError` mentioning "72 bytes" on a password that is nowhere near 72 bytes long.

### Pitfall 2: bcrypt's real 72-byte limit (if bcrypt is ever used as the hash instead of Argon2)
**What goes wrong:** bcrypt silently truncates (and historically, truncates at the first NUL byte in) any password material beyond 72 bytes — a long passphrase or a password containing multi-byte UTF-8 characters near the boundary can silently lose entropy with no error at all.
**Why it happens:** bcrypt's underlying Blowfish-based algorithm has a hard 72-byte input ceiling; this is a property of the algorithm, not a library bug.
**How to avoid:** Prefer Argon2 (via `pwdlib[argon2]`, no such ceiling) as this research recommends; if bcrypt is ever chosen instead, enforce a maximum password length well under 72 bytes at the sign-up form level so truncation can never silently occur.
**Warning signs:** Two different-looking long passwords sharing the same first 72 bytes both successfully authenticate.

### Pitfall 3: Hardcoded `secure=True` breaks `TestClient`-based auth tests
**What goes wrong:** FastAPI's `TestClient` (httpx-based) defaults to a `http://testserver` base URL. A cookie set with a hardcoded `secure=True` will not be resent by httpx's cookie jar on the next request in the same test (since the request scheme is `http`, not `https`), making it look like the session "didn't persist" even though the code is correct in production.
**Why it happens:** The `Secure` cookie attribute is scheme-gated by design (browsers and RFC-6265-compliant clients, including httpx, only attach a `Secure` cookie to an `https://` request).
**How to avoid:** Derive `secure=` from the live request's scheme (`request.url.scheme == "https"`, see Pattern 2) instead of a hardcoded literal or a `"localhost" in hostname` string match (which would also mis-handle `testserver` and any non-localhost dev hostname); this way `TestClient`'s default `http://testserver` naturally produces `secure=False` cookies that round-trip correctly in tests, with zero test-only conditional code.
**Warning signs:** A `test_signin_then_confirm_succeeds`-style test where `client.post("/api/confirm", ...)` returns 401 immediately after a successful-looking `client.post("/api/auth/login", ...)` in the same `TestClient` instance.

### Pitfall 4: CORS `allow_credentials=True` + wildcard origin/headers is rejected outright by browsers
**What goes wrong:** If a future change widens `CORSMiddleware`'s `allow_origins`/`allow_headers` to `["*"]` while `allow_credentials=True` stays set (as it already is in `api/app.py`'s dev-CORS block), browsers reject the response entirely — cookies never arrive, and the failure mode looks like "the cookie isn't being sent" rather than a CORS spec violation.
**Why it happens:** The CORS spec explicitly forbids combining a wildcard origin/header list with `Access-Control-Allow-Credentials: true`.
**How to avoid:** Keep the existing explicit `allow_origins=["http://localhost:5173"]` (already correct in `api/app.py`) — do not widen it to a wildcard while `allow_credentials=True` remains set; this is a "don't regress" note, not a new gap.
**Warning signs:** Confirm requests silently fail only when the frontend and backend run on different ports (i.e., only in the `ASSAYINGEST_DEV_CORS=1` raw cross-origin mode, not through the Vite proxy).

### Pitfall 5: Confusing the Vite-proxy dev setup for a genuinely cross-origin cookie scenario
**What goes wrong:** A developer might assume `SameSite=Lax` will block the cookie in dev because the frontend (`:5173`) and backend (`:8000`) are different ports, and over-engineer a `SameSite=None; Secure` workaround.
**Why it happens:** `SameSite` cookie classification is based on the registrable **site** (scheme + eTLD+1), which ignores port — `localhost:5173` and `localhost:8000` are the *same site* for SameSite purposes, even though they are different *origins* for CORS purposes. Additionally, `frontend/vite.config.ts` already proxies `/api/*` to `http://localhost:8000` (`changeOrigin: true`), so in the normal dev flow (`npm run dev`, no `ASSAYINGEST_DEV_CORS`) the browser only ever talks to `:5173` — it is genuinely same-origin from the cookie's point of view, and `credentials: 'include'` is a defensive no-op there, not a requirement.
**How to avoid:** Keep `SameSite=Lax` (matches D-06-01 exactly); add `credentials: 'include'` to `lib/api.ts`'s shared `request()` helper anyway (it is required for the `ASSAYINGEST_DEV_CORS=1` raw cross-origin path some contributors may use, and it is harmless under the Vite proxy and the built same-process demo).
**Warning signs:** None expected if the recommendation above is followed — this pitfall is about *avoiding unnecessary complexity*, not fixing a live bug.

### Pitfall 6: Verification-token replay
**What goes wrong:** If the verify endpoint only checks the token's signature and expiry (via `itsdangerous.loads(..., max_age=...)`) but never marks anything as "consumed," the same emailed/console-printed link can be replayed indefinitely within its `max_age` window — usually harmless for a one-way "mark verified" flip (idempotent), but worth being deliberate about.
**Why it happens:** `itsdangerous` tokens are stateless by design — validity is purely a function of signature + timestamp, with no server-side revocation list.
**How to avoid:** Since D-06-04's verify action is idempotent (setting `is_verified=True` a second time changes nothing), a stateless token is an acceptable choice here and does **not** need a `used_at` column — but document this reasoning inline in the token module's docstring so a future reader doesn't assume single-use enforcement exists in the token layer.
**Warning signs:** A requirement change to something non-idempotent (e.g. "each verify link can only ever be used once, log a security event on reuse") would need a persisted per-token `used_at` timestamp instead — flagged as a design decision to revisit if that requirement appears later.

## Code Examples

### `UserStore` ABC + `SqliteUserStore` (mirrors `learning/store.py` + `learning/sqlite_store.py` exactly)

```python
# Source: this codebase's own learning/store.py + learning/sqlite_store.py +
# learning/sqlite_field_set_store.py (all read this session) -- [VERIFIED:
# codebase grep, this is a direct structural mirror, not an external claim]

# src/assayingest/auth/models.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    """A signed-up/OAuth-provisioned user -- pure Python, no dependency on
    pandas/Anthropic/any wire format (mirrors domain/models.py's own
    convention). `password_hash` is None for a Google-OAuth-only account
    (D-06-05: OAuth users never set a local password)."""

    id: str
    email: str
    password_hash: str | None
    is_verified: bool
    auth_provider: str  # "password" | "google"
    created_at: str


# src/assayingest/auth/store.py
from __future__ import annotations

from abc import ABC, abstractmethod

from .models import User


class UserStore(ABC):
    """The seam a Postgres-backed store (a future phase) would implement
    identically -- mirrors learning/store.py::ProfileStore's docstring."""

    @abstractmethod
    def save(self, user: User) -> None:
        """Persist `user`, upserting on an identical `email` (never `id`,
        since `id` is minted fresh on first save)."""

    @abstractmethod
    def get(self, user_id: str) -> User | None: ...

    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    def mark_verified(self, user_id: str) -> None: ...


# src/assayingest/auth/sqlite_store.py
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from ..learning.sqlite_store import _DEFAULT_DB_PATH  # same file, D-06-02
from .models import User
from .store import UserStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    password_hash TEXT,
    is_verified INTEGER NOT NULL DEFAULT 0,
    auth_provider TEXT NOT NULL DEFAULT 'password',
    created_at TEXT NOT NULL,
    UNIQUE(email)
);
"""


class SqliteUserStore(UserStore):
    def __init__(self, db_path: str | Path = _DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._path)) as conn:
            conn.executescript(_SCHEMA)

    def save(self, user: User) -> None:
        with closing(sqlite3.connect(self._path)) as conn, conn:
            conn.execute(
                "INSERT INTO users "
                "(id, email, password_hash, is_verified, auth_provider, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(email) DO UPDATE SET "
                "password_hash=excluded.password_hash, "
                "is_verified=excluded.is_verified, "
                "auth_provider=excluded.auth_provider",
                (
                    user.id, user.email, user.password_hash,
                    int(user.is_verified), user.auth_provider, user.created_at,
                ),
            )

    def get(self, user_id: str) -> User | None:
        with closing(sqlite3.connect(self._path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row is not None else None

    def get_by_email(self, email: str) -> User | None:
        with closing(sqlite3.connect(self._path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return _row_to_user(row) if row is not None else None

    def mark_verified(self, user_id: str) -> None:
        with closing(sqlite3.connect(self._path)) as conn, conn:
            conn.execute("UPDATE users SET is_verified = 1 WHERE id = ?", (user_id,))


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"], email=row["email"], password_hash=row["password_hash"],
        is_verified=bool(row["is_verified"]), auth_provider=row["auth_provider"],
        created_at=row["created_at"],
    )
```

### Password hashing seam

```python
# Source: pwdlib's own official usage example (github.com/frankie567/pwdlib,
# frankie567.github.io/pwdlib/guide/) -- [CITED: pwdlib official docs, MEDIUM
# confidence, WebSearch this session]

# src/assayingest/auth/passwords.py
from __future__ import annotations

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()  # Argon2id, bcrypt fallback for verify-only


def hash_password(plain: str) -> str:
    return _password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _password_hash.verify(plain, hashed)
```

### Console-printed verification link (AUTH-03)

```python
# src/assayingest/api/routes/auth.py (signup handler, excerpt)
import logging

logger = logging.getLogger("assayingest.auth")


def _print_verification_link(request: Request, user_id: str) -> None:
    token = create_verification_token(user_id)
    verify_url = str(request.url_for("verify_email")) + f"?token={token}"
    # Log-or-raise, never both (CLAUDE.md convention); this IS the
    # "email", so it goes to the server console via the app logger, not
    # stdout print() directly, matching this project's existing logging
    # discipline elsewhere.
    logger.info("Verification link for %s: %s", user_id, verify_url)
```

### pytest: session-cookie auth end-to-end with `TestClient`

```python
# Source: httpx/FastAPI TestClient's documented persistent cookie jar
# behavior (fastapi.tiangolo.com/reference/testclient/) -- [CITED: FastAPI
# docs, MEDIUM confidence, WebSearch this session] + this codebase's own
# tests/api/test_confirm_gate.py dependency-override idiom (read this
# session) -- [VERIFIED: codebase grep]

def test_signin_required_to_confirm(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    from assayingest.api.app import app
    from assayingest.api.deps import get_user_store
    from assayingest.auth.sqlite_store import SqliteUserStore

    store = SqliteUserStore(tmp_path / "users.db")
    app.dependency_overrides[get_user_store] = lambda: store
    client = TestClient(app)  # one instance -- cookie jar persists across calls

    # Signed out: the server-side gate rejects with 401, not a UI-only block.
    response = client.post("/api/confirm", json={...})
    assert response.status_code == 401

    client.post("/api/auth/signup", json={"email": "a@b.com", "password": "longenough"})
    # AUTH-03: capture the console-printed link instead of an email inbox.
    # (capsys/caplog fixture reads the logger output; verify via the token
    # directly for a unit-level test, or via caplog for the true console-print
    # assertion the CONTEXT.md success criteria call out.)
    login_response = client.post(
        "/api/auth/login", json={"email": "a@b.com", "password": "longenough"}
    )
    assert "di_session" in login_response.cookies  # Set-Cookie was issued

    # Signed in but NOT verified yet -- confirm is still blocked (403, not 401).
    response = client.post("/api/confirm", json={...})
    assert response.status_code == 403
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|-------------------|---------------|--------|
| `passlib` as the default Python password-hashing wrapper | `pwdlib` (Argon2-first, maintained) | `passlib`'s last release is roughly 3 years old and it errors on import under recent Python (3.11+ deprecates the `crypt` module `passlib` depends on for some backends); `pwdlib` was created specifically to fill this gap and is now `fastapi-users`' own default | Do not add `passlib` to this project; use `pwdlib[argon2]` |
| bcrypt as the "obvious" password hash choice | Argon2id preferred by OWASP for new projects | OWASP's Password Storage Cheat Sheet has recommended Argon2id (or scrypt) over bcrypt for new systems for several years now | Reinforces the `pwdlib[argon2]` choice over a raw `bcrypt` dependency |

**Deprecated/outdated:** `passlib` — unmaintained, Python-3.13-fragile; do not introduce it into this project even though D-06-03 lists it as an option planners may pick, since a maintained, purpose-built modern alternative (`pwdlib`) already exists and is directly named in the pwdlib project's own "why we built this" rationale.

## Assumptions Log

> No MCP-based provider (Context7/Ref/Jina/Exa/etc.) was available in this session's tool set — every finding below rests on the built-in `WebSearch` tool plus this session's own `uv pip install --dry-run` PyPI resolution (a genuine tool-verified fact, not training-data recall) and direct reads of this repository's own source. Package **versions** (2.2.0 / 0.3.0 / 1.7.2 / 25.1.0) are `[VERIFIED: uv resolver against the live PyPI index]`. Package **existence/identity/choice** (i.e., that `itsdangerous`/`pwdlib`/`authlib` are the right packages to reach for) is `[ASSUMED]` per the package-name-provenance rule, even where WebSearch surfaced an official docs URL, because no Context7/authoritative-fetch tool confirmed it this session.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `itsdangerous` is the correct/standard choice for signing the session cookie and the verification token (vs. Starlette `SessionMiddleware` or a JWT library) | Standard Stack, Architecture Patterns §2 | Low — `itsdangerous` is extremely well-established (Pallets ecosystem, underlies Starlette's own `SessionMiddleware`); even if the planner picks `SessionMiddleware` instead (explicitly allowed by D-06-01), the cookie-flag requirements (HttpOnly/SameSite=Lax/Secure) are identical either way |
| A2 | `pwdlib[argon2]` is currently the best-practice replacement for `passlib`, and is what `fastapi-users` defaults to | Standard Stack, State of the Art | Medium — this is asserted from a WebSearch summary of the pwdlib project's own discussion thread and `fastapi-users` docs, not a direct Context7 doc fetch this session; if wrong, `argon2-cffi` used directly (no `pwdlib` wrapper) is a safe fallback with identical security properties, just a slightly less convenient API |
| A3 | Authlib's exact `oauth.register(...)`/`authorize_redirect`/`authorize_access_token` method names and the requirement that `SessionMiddleware` back the OAuth state/nonce | Architecture Patterns §3 | Medium — sourced from WebSearch summaries of `docs.authlib.org`, not a direct page fetch this session; the planner/implementer should open `docs.authlib.org/en/latest/client/fastapi.html` directly before writing the route bodies, since this is the area of highest exact-API-shape uncertainty in this research |
| A4 | The `Secure` cookie flag is what breaks `TestClient`-based session tests when hardcoded `True`, and that deriving it from `request.url.scheme` is the fix | Common Pitfalls #3 | Low-Medium — corroborated by a GitHub issue (`fastapi/fastapi#3339`, "Secure/HTTPOnly cookies untestable") surfaced directly in WebSearch results, but not independently reproduced in this session |
| A5 | `SameSite` classification for cookies is based on registrable site (ignoring port), so `localhost:5173`↔`localhost:8000` count as same-site even though CORS treats them as separate origins | Common Pitfalls #5 | Low — this is standard, stable web-platform behavior (RFC 6265bis / Same-Site cookies spec), high-confidence training knowledge, but not independently fetched from a spec document this session |
| A6 | The four PyPI packages flagged `[SUS]` by the legitimacy tool are, in fact, legitimate, well-established projects (Pallets, pyca-adjacent, `fastapi-users` maintainer, Authlib org) | Package Legitimacy Audit | Low — corroborated by official GitHub org/repo URLs surfaced directly in WebSearch results, but the planner must still gate each install behind `checkpoint:human-verify` per protocol regardless of this corroboration |

**If this table is empty:** N/A — see entries above; none of this research should be treated as fully verified fact without the planner (or the human) opening the cited official-docs URLs directly, especially A3 (Authlib's exact API surface).

## Open Questions

1. **Where does `SESSION_SECRET` come from in a fresh checkout, and what happens if it's unset?**
   - What we know: D-06-06/canonical_refs asks for a `SESSION_SECRET` placeholder in `.env.example`; Pattern 2 above raises `RuntimeError` if unset at first use.
   - What's unclear: Whether the planner wants a dev-mode auto-generated ephemeral secret (sessions invalidate on every restart — acceptable for an overnight demo) vs. a hard requirement to set one before the app starts at all.
   - Recommendation: Raise loudly and require it explicitly (current Pattern 2 design) — matches this codebase's existing "fail loud on missing config" convention (`MissingCredentialsError` for `ANTHROPIC_API_KEY`) rather than silently generating a secret that would invalidate every session on restart without explanation.

2. **Does an OAuth-provisioned (`auth_provider="google"`) user need email verification at all?**
   - What we know: D-06-04 only discusses the password sign-up path; Google's own OAuth flow already asserts a verified email address in the ID token (`email_verified` claim) for most Google accounts.
   - What's unclear: Whether Phase 06 should mark a Google-OAuth-created `User` as `is_verified=True` immediately (skipping the console-link step entirely for that path), or still route it through the same flag.
   - Recommendation: Trust Google's `email_verified` claim from the ID token/userinfo response and set `is_verified=True` at OAuth-callback time — re-verifying an already-IdP-verified email via a second, self-issued console link adds no security value and would be a confusing UX given the flag is off by default anyway.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|-------------------|
| V2 Authentication | yes | `pwdlib[argon2]` for password hashing; minimum 8-char length rule (D-06-03, ASVS L1); no password composition rules beyond length (over-engineering explicitly rejected by D-06-03) |
| V3 Session Management | yes | `itsdangerous`-signed, `HttpOnly` + `SameSite=Lax` + scheme-derived `Secure` cookie (Pattern 2); session invalidated by cookie deletion on sign-out; no server-side session table needed at L1 since the signed token is itself the sole credential and has a bounded `max_age` |
| V4 Access Control | yes | `require_user`/`require_verified_user` FastAPI dependencies enforced server-side on every governed endpoint (P1); never trust a client-sent "signed in"/"verified" claim |
| V5 Input Validation | yes | Pydantic wire models (`SignUpIn`/`SignInIn`) at the API boundary, mirroring `api/wire.py`'s existing convention; email format validated via Pydantic's `EmailStr` (requires the `email-validator` package — note as an additional transitive dependency if used) or a simple regex if the planner prefers zero new deps |
| V6 Cryptography | yes | Password hashing delegated entirely to `pwdlib[argon2]` (Argon2id) — never hand-rolled (see Don't Hand-Roll); session/verification tokens delegated to `itsdangerous` (HMAC-SHA1-based signing under the hood) — never hand-rolled |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Session cookie theft via XSS | Information Disclosure | `HttpOnly` flag (already locked by D-06-01) — JS can never read the cookie even if an XSS bug exists elsewhere |
| CSRF against a governed POST (e.g. `/api/confirm`) | Spoofing / Tampering | `SameSite=Lax` blocks the cookie from being attached to cross-site POSTs initiated by a third-party page (Lax still allows top-level GET navigations, which is the standard, accepted tradeoff for this cookie policy) |
| Credential stuffing / brute-force login | Spoofing | Out of scope for this phase per D-06-03 ("do not over-engineer policy, ASVS L1") — no rate-limiting is specified; flag as a known gap, not silently addressed |
| OAuth CSRF (authorization-code interception / state forgery) | Spoofing / Tampering | Authlib's `authorize_redirect`/`authorize_access_token` handle `state` (and OIDC `nonce`) validation internally — this is precisely why Authlib is used instead of hand-rolled `httpx` calls (Don't Hand-Roll) |
| Password hash disclosure via logging | Information Disclosure | Never log `password` or `password_hash` — `passwords.py`'s functions take/return only the values needed, and no route handler should ever `logger.info(...)` a request body containing a password field |
| Timing attack on password comparison | Information Disclosure | Delegated to `pwdlib`/`argon2-cffi`'s constant-time comparison internals — never a hand-rolled `==` check |

## Sources

### Primary (HIGH confidence)
- This repository's own source, read directly this session: `src/assayingest/api/{app,deps,state,wire}.py`, `src/assayingest/api/routes/confirm.py`, `src/assayingest/service.py`, `src/assayingest/learning/{store,sqlite_store,sqlite_field_set_store,field_set_store}.py`, `src/assayingest/domain/models.py`, `src/assayingest/fields/models.py`, `src/assayingest/export/writers.py`, `frontend/src/lib/api.ts`, `frontend/src/state/upload.ts`, `frontend/src/components/{AppShell,ConfirmGate}.tsx`, `frontend/vite.config.ts`, `pyproject.toml`, `tests/api/test_confirm_gate.py`, `.env.example` (via `git show HEAD:.env.example`).
- `uv pip install --dry-run` resolved directly against the live PyPI index this session (2026-07-11): `itsdangerous==2.2.0`, `pwdlib==0.3.0`, `argon2-cffi==25.1.0`, `authlib==1.7.2`, `bcrypt==5.0.0`, `pyjwt==2.13.0` (the last two are documented alternatives, not this research's recommendation).
- `gsd-tools query package-legitimacy check --ecosystem pypi` run directly this session for `itsdangerous`, `bcrypt`, `argon2-cffi`, `authlib`, `pwdlib`, `pyjwt`.

### Secondary (MEDIUM confidence)
- WebSearch results referencing official documentation URLs: `docs.authlib.org/en/latest/client/{starlette,fastapi}.html`, `fastapi.tiangolo.com/{tutorial/cors,advanced/response-cookies,reference/testclient}`, `github.com/frankie567/pwdlib` (+ discussion #1), `frankie567.github.io/pwdlib/guide/`, `github.com/pyca/bcrypt/issues/1082` and `#1079`.

### Tertiary (LOW confidence)
- General WebSearch summaries not tied to an official docs/repo URL (e.g. generic FastAPI-session blog posts on itsdangerous usage) — used only to corroborate the overall pattern shape, not any exact API signature.

## Metadata

**Confidence breakdown:**
- Standard stack (library choices): MEDIUM — package identities are WebSearch-derived (no Context7/MCP this session, so `[ASSUMED]` per the package-name-provenance rule); versions are tool-verified against live PyPI.
- Architecture (DI seam, UserStore mirror, confirm threading): HIGH — directly derived from this codebase's own existing, read source code, not an external claim.
- OAuth wiring specifics (Authlib exact API calls): MEDIUM — WebSearch-derived from official docs URLs, but not independently fetched/executed this session; flagged as Open Question / Assumption A3, planner should open the Authlib docs directly before implementing.
- Pitfalls (bcrypt 72-byte, TestClient Secure-cookie, SameSite/port): MEDIUM — each corroborated by a specific GitHub issue or official doc surfaced in WebSearch results.

**Research date:** 2026-07-11
**Valid until:** 30 days (stable ecosystem; Authlib/pwdlib/itsdangerous release cadence is slow, but re-verify exact Authlib API calls against `docs.authlib.org` directly before implementation given no direct fetch was performed this session)
