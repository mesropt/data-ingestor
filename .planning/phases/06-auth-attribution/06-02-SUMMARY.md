---
phase: 06-auth-attribution
plan: 02
subsystem: auth
tags: [fastapi, itsdangerous, pwdlib, authlib, session-cookie, oauth, feature-flag, tdd]

# Dependency graph
requires:
  - phase: 06-01
    provides: "auth/ package (User, UserStore, SqliteUserStore), password/session/verification-token seams, deps.py gates (get_current_user/require_user/require_verified_user, get_user_store)"
  - phase: 04-api-and-shell
    provides: "FastAPI app, deps.py DI seam, /api/confirm route, api.state registry, service.confirm, export.build_manifest"
provides:
  - "api/routes/auth.py: signup, login, logout, verify, config, me (email/password + config surface)"
  - "Feature-flagged Google OAuth routes (google/login, google/callback) returning 501 when DATA_INGESTOR_GOOGLE_OAUTH is off"
  - "Conditional Starlette SessionMiddleware (registered only when the OAuth flag is on)"
  - "Server-side auth gate on /api/confirm (require_verified_user: 401 signed-out / 403 unverified)"
  - "confirmed_by attribution threaded through service.confirm -> build_manifest (AUTH-04)"
affects: [06-03-frontend-auth, 07-schema-crud, alias-provenance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One APIRouter per concern with prefix=/api/auth; flag checked FIRST in OAuth handlers before any secret env read"
    - "cookie secure= derived from request.url.scheme=='https' (never hardcoded) so TestClient http round-trips"
    - "conditional middleware registration mirroring the existing ASSAYINGEST_DEV_CORS block"
    - "additive keyword-only param (confirmed_by) so every existing CLI call site is unaffected"

key-files:
  created:
    - src/assayingest/api/routes/auth.py
    - tests/api/test_auth_routes.py
    - tests/api/test_google_oauth_flag.py
    - tests/api/test_confirm_auth_gate.py
  modified:
    - src/assayingest/api/wire.py
    - src/assayingest/api/app.py
    - src/assayingest/api/routes/confirm.py
    - src/assayingest/service.py
    - src/assayingest/export/writers.py
    - tests/api/test_confirm_gate.py
    - tests/api/test_money_shot.py
    - tests/test_service.py

decisions:
  - "Verification link points at the SPA landing path /verify?token= (not /api/auth/verify) per the task action's MUST directive, so opening the console link renders the frontend VerifyLanding (plan 06-03) rather than raw JSON; the SPA then calls GET /api/auth/verify"
  - "Minimal email sanity check (single @ with non-empty local/domain) via a Pydantic field_validator instead of adding the email-validator dependency (ASVS L1, D-06-03 do-not-over-engineer)"
  - "409 Conflict for a duplicate-email signup (plan-check WARNING resolution); never an upsert over the existing account"
  - "Only the two existing test files that actually POST /api/confirm (test_confirm_gate.py, test_money_shot.py) were updated with a verified-user override; the other two the plan named do not call /api/confirm and stayed green untouched"

# Metrics
duration: ~9 min
completed: 2026-07-11
status: complete

requirements-completed: [AUTH-01, AUTH-02, AUTH-03, AUTH-04]
---

# Phase 6 Plan 2: Auth HTTP Surface & Confirm Gate Summary

**Wired the full email/password auth HTTP surface (signup with console-printed verification link, login setting the itsdangerous-signed di_session cookie, logout, email verify, /api/auth/config, /me) plus feature-flagged Google OAuth (501 when off), then applied the server-side `require_verified_user` gate to /api/confirm and threaded `confirmed_by=user.email` into the manifest — all TDD, all four AUTH requirements delivered, zero live provider secret required.**

## Performance

- **Duration:** ~9 min (2026-07-11T13:40:52Z → 13:50:11Z)
- **Tasks:** 3 (all TDD: test → feat)
- **Files:** 12 (4 created, 8 modified)
- **Tests:** full suite 510 passed, 4 skipped (pre-existing live-test skips); +20 new tests over the 06-01 baseline of 490

## Accomplishments

- **Task 1 — email/password routes + config.** Added `SignUpIn` (>=8-char password guard + minimal email validator), `SignInIn`, `UserOut` (never exposes `password_hash`), `SignUpAcceptedOut`, `AuthConfigOut` to `wire.py`. Created `api/routes/auth.py` with `signup` (201, hashes via pwdlib, mints a verification token, logs the SPA verify link to the `assayingest.auth` logger — the dev "email"; duplicate email → 409), `login` (verifies against the Argon2 hash, sets the HttpOnly `di_session` cookie with `secure` derived from the request scheme, unverified users still allowed in per D-06-04, wrong password → 401 with no cookie), `logout` (clears the cookie), `verify` (`verified`/`expired` JSON status the SPA branches on), `config`, and `me`. Registered the router before the frontend catch-all. Password is never logged (grep gate passes).
- **Task 2 — feature-flagged Google OAuth.** Added `google/login` and `google/callback` to the same router; both check `google_oauth_enabled()` FIRST and return 501 before any client-id/secret env read, so the routes are import-safe and callable with no secrets present. When on, they build the Authlib OIDC registry, redirect/exchange, `get_or_create_by_email` (trusting Google's `email_verified`, with an inline comment noting the assumption), set the session cookie, and redirect to the SPA. `app.py` registers Starlette `SessionMiddleware` only when the flag is on (mirroring the `ASSAYINGEST_DEV_CORS` conditional block) — the overnight flag-off app starts with zero extra middleware.
- **Task 3 — confirm gate + attribution.** `confirm.py` now takes `user: User = Depends(require_verified_user)`, so a signed-out request is 401 and an unverified one 403 before any registry/gate work (D-06-06, T-06-06); it passes `confirmed_by=user.email` into `service.confirm`. `service.confirm` and `export.build_manifest` gained an additive keyword-only `confirmed_by: str | None = None` recorded in the manifest (None on the CLI path). Identity is taken only from the server-resolved `User`, never a client body field (T-06-07).

## Task Commits

1. Task 1 RED — `8ed55f5` (test)
2. Task 1 GREEN — `b29b8a3` (feat)
3. Task 2 RED — `2eaf064` (test)
4. Task 2 GREEN — `5d41758` (feat)
5. Task 3 RED — `1497741` (test)
6. Task 3 GREEN — `7e62186` (feat)

## Decisions Made

- **Verification link → SPA path.** The task action mandated (MUST) the console link target the SPA landing `/verify?token=` so it renders VerifyLanding (plan 06-03), not raw JSON. The Task 1 behavior line phrased the log assertion as containing `/api/auth/verify`; these are mutually exclusive substrings. Honored the action's explicit MUST and its downstream dependency — the RED test asserts the logged URL contains `verify?token=` and a non-empty token, and the verify test extracts that token from the log to drive `GET /api/auth/verify`. See Deviations.
- **No new dependency for email validation.** Used a Pydantic `field_validator` (single `@`, non-empty local/domain) rather than `EmailStr` + `email-validator`, per the plan's explicit executor-discretion note and D-06-03's "do not over-engineer".
- **409 for duplicate signup**, per the plan-check WARNING resolution.

## Deviations from Plan

### 1. [Reconciliation] Verification-link log path — action's SPA path honored over the behavior line's `/api/auth/verify`

- **Found during:** Task 1 (RED authoring).
- **Issue:** The task `<behavior>` said assert the log contains `/api/auth/verify`, but the `<action>` explicitly (MUST) required logging the SPA landing path `f"{request.base_url}/verify?token={token}"` so the human-clicked link renders the frontend VerifyLanding (a 06-03 dependency). Both cannot be the logged substring.
- **Resolution:** Implemented and tested the SPA path (`/verify?token=`), since the action is the authoritative implementation spec with a stated downstream dependency. The distinct API endpoint `GET /api/auth/verify` is still what the SPA calls and is tested directly.
- **Files:** src/assayingest/api/routes/auth.py, tests/api/test_auth_routes.py.
- **Commits:** 8ed55f5, b29b8a3.

### 2. [Scope correction] Only two of the four named existing test files actually POST /api/confirm

- **Found during:** Task 3.
- **Issue:** The plan named four files to update for the new gate (`test_confirm_gate.py`, `test_hint_and_export.py`, `test_upload.py`, `test_money_shot.py`). A grep for `"/api/confirm"` showed only `test_confirm_gate.py` and `test_money_shot.py` POST to it; `test_hint_and_export.py` (structural-hint/resolve + export download) and `test_upload.py` (upload only) never hit the gated route.
- **Resolution:** Injected the verified-user override (`app.dependency_overrides[require_verified_user]`) into only the two files that needed it; the other two remained green untouched. No behavior was weakened. Extended `test_confirm_gate.py`'s happy path to also assert `manifest.confirmed_by == "curator@example.com"`.
- **Files:** tests/api/test_confirm_gate.py, tests/api/test_money_shot.py.
- **Commit:** 7e62186.

## TDD Gate Compliance

Each of the 3 tasks has a `test(...)` commit preceding its `feat(...)` commit (6 commits total). RED runs were confirmed failing before implementation (404/200-via-SPA-fallback for missing routes; `TypeError: unexpected keyword argument 'confirmed_by'` for the additive seam).

## Threat Surface

All new surface matches the plan's `<threat_model>`: the confirm gate (T-06-06), server-resolved `confirmed_by` (T-06-07), flag-gated OAuth with conditional SessionMiddleware (T-06-08), and verify-link-not-password logging (T-06-09, grep gate passes). No new unlisted trust boundary introduced. Accepted-risk items (T-06-10 CSRF via SameSite=Lax, T-06-11 no login rate-limiting at ASVS L1) are unchanged and remain known gaps for a future phase.

## User Setup Required

For a live (non-test) run the developer must set a real `SESSION_SECRET` in the gitignored `.env` (e.g. `python -c 'import secrets; print(secrets.token_urlsafe(32))'`) — the session/verification cookie seams fail loud without it. Google OAuth stays off (no secret needed) unless `DATA_INGESTOR_GOOGLE_OAUTH=1` plus real `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are provided.

## Next Phase Readiness

- 06-03 (frontend auth) can consume `/api/auth/{signup,login,logout,verify,config,me}` and the `google_oauth_enabled` flag directly; the console-printed link already points at the SPA `/verify` landing this plan assumed.
- `confirmed_by` is now present in both the `manifest.json` export and the `ConfirmResponse.manifest`, ready for Phase 07's alias-provenance crosswalk (no crosswalk built here, per D-06-06).

## Self-Check: PASSED

All 4 created source/test files exist on disk; all 6 task commits (8ed55f5, b29b8a3, 2eaf064, 5d41758, 1497741, 7e62186) present in git log. TDD gate sequence satisfied per task (test → feat). Full suite: 510 passed, 4 skipped.
