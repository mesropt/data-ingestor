---
phase: 06-auth-attribution
verified: 2026-07-11T00:00:00Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
autonomous_acceptance: "All 4 success criteria code+test verified (510 passed). Browser-only UI checks below deferred to the milestone-end human UAT pass (human_verify_mode=end-of-phase) per the autonomous overnight mandate — status advanced to passed with human_verification retained for the user's morning review."
re_verification:
human_verification:
  - test: "In a browser (dev build), sign up with a new email; watch the SERVER CONSOLE for the printed verification link; open it and confirm the Verify Landing shows 'Email Verified'."
    expected: "Sign-up view shows the amber 'Check your server console for your verification link' notice; the server log prints a /verify?token=... URL; opening it renders VerifyLanding with the success-green 'Email Verified' state."
    why_human: "End-to-end browser rendering of the console-notice + VerifyLanding visual states cannot be observed by grep/tests (the API-level verify path IS covered by test_verify_with_a_fresh_token_marks_the_user_verified)."
  - test: "While signed OUT, open the Review screen and observe the Confirm affordance; then sign in as a verified user and observe it change."
    expected: "Signed out → an actionable 'Sign In to Confirm' outline button (ShieldAlert) that routes to Sign In carrying returnTo; signed-in-unverified → disabled with a verify tooltip; signed-in-verified+ready → enabled Confirm. Server still re-checks (401/403) regardless of the button."
    why_human: "The four mutually-exclusive ConfirmGate UI tiers and the returnTo round-trip are visual/interaction behavior; the server-side gate itself is fully tested (test_confirm_signed_out_returns_401, test_confirm_signed_in_unverified_returns_403)."
  - test: "With DATA_INGESTOR_GOOGLE_OAUTH unset (default), confirm the 'Sign in with Google' button is ABSENT from the auth views. Optionally set the flag on and confirm the button appears."
    expected: "Flag off (default) → no Google button rendered anywhere (GoogleSignInButton returns null); flag on → the placeholder-icon button appears. The overnight app runs with no OAuth secret."
    why_human: "Conditional button rendering driven by the mount-time /api/auth/config probe is browser-observable; the backend flag behavior (501 off, config reports flag) is fully tested."
  - test: "Sign in as a verified curator, confirm a mapping, and confirm the identity chip + Sign Out appear in the AppShell; sign out and confirm the chip clears."
    expected: "SignedInIndicator shows the truncated mono email + icon-only Sign Out; a 'Signed in as {email}.' / 'Signed out.' toast fires; after sign-out the governed action is gated again."
    why_human: "AppShell identity chip, toasts, and sign-out interaction are visual/real-time; the auth store reducer + selectors are unit-tested (73 vitest tests) and the server /me + logout paths are covered."
---

# Phase 6: Auth & Attribution Verification Report

**Phase Goal:** Add an authentication + session + identity layer so every governed action (confirming a mapping) requires a signed-in, named user — enforced server-side — while staying runnable overnight with no live provider secrets, and making the authenticated identity available for downstream provenance.
**Verified:** 2026-07-11
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth (Success Criterion) | Status | Evidence |
|---|---------------------------|--------|----------|
| 1 | AUTH-01 — Account creation + sign-in works; confirming a mapping is blocked SERVER-SIDE when signed out (401), not UI-only | ✓ VERIFIED | `deps.py:79` `require_user` raises 401; `confirm.py:46` `user: User = Depends(require_verified_user)`; `test_confirm_signed_out_returns_401_and_persists_nothing` asserts 401 + nothing persisted; `test_login_with_correct_credentials_sets_cookie_that_round_trips_to_me` covers sign-in |
| 2 | AUTH-03 — Email verification completes via a link the dev build PRINTS TO SERVER CONSOLE; no live email provider | ✓ VERIFIED | `auth.py:119-120` logs `/verify?token=...` to `assayingest.auth` logger (never the password); `test_signup_...logs_the_console_verification_link` asserts the logged URL; `test_verify_with_a_fresh_token_marks_the_user_verified` extracts the token FROM THE LOG and drives `GET /api/auth/verify` to `is_verified=True` |
| 3 | AUTH-02 — "Sign in with Google" behind a feature flag OFF by default with placeholder creds; app runs end-to-end with no live OAuth secret (flag off → 501 / button absent) | ✓ VERIFIED | `auth.py:54-57` `google_oauth_enabled()` reads flag (default off); `auth.py:216-239` both Google routes check the flag FIRST and return 501; `app.py:50` SessionMiddleware registered only when flag on; `test_google_login/callback_returns_501_when_the_flag_is_off`, `test_app_imports_and_starts_with_no_session_middleware_when_flag_off`; frontend `GoogleSignInButton.tsx:27-28` returns null when `!enabled`; `.env.example` carries all 4 placeholders |
| 4 | AUTH-04 — Signed-in user's identity recorded and available downstream (confirmed_by threaded confirm → service.confirm → build_manifest) | ✓ VERIFIED | `confirm.py:95` passes `confirmed_by=user.email` (server-resolved, never client body); `service.py:270,312` threads keyword-only `confirmed_by` into `build_manifest`; `writers.py:102` `"confirmed_by": confirmed_by` in manifest; `test_confirm_verified_user_records_confirmed_by_email_in_the_manifest` asserts `manifest["confirmed_by"] == "curator@example.com"` |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/assayingest/auth/` (models/store/sqlite_store/passwords/session/tokens) | Auth substrate: User model, UserStore, Argon2 hashing, salted session + verification tokens | ✓ VERIFIED | All present; SqliteUserStore mirrors learning store seam; wired into deps.py |
| `src/assayingest/api/deps.py` | get_user_store, get_current_user (never raises), require_user (401), require_verified_user (403) | ✓ VERIFIED | `deps.py:52-97`; imported + used by auth.py and confirm.py |
| `src/assayingest/api/routes/auth.py` | signup/login/logout/verify/config/me + flag-gated Google routes | ✓ VERIFIED | All routes present and registered (`app.py:26`); credential checks server-side |
| `src/assayingest/api/routes/confirm.py` | `/api/confirm` gated by require_verified_user; confirmed_by threaded | ✓ VERIFIED | `confirm.py:46,95` |
| `src/assayingest/service.py` + `export/writers.py` | confirmed_by keyword-only param → manifest | ✓ VERIFIED | `service.py:270,312`; `writers.py:77,102` |
| `frontend/src/state/auth.ts` | authReducer + isSignedIn/isVerified/isGovernedActionAllowed | ✓ VERIFIED | Selectors present (`auth.ts:66-79`); 73 vitest tests green |
| `frontend/src/lib/api.ts` | 6 auth wrappers + credentials:'include' on every fetch | ✓ VERIFIED | `api.ts:60,118` credentials on request() + uploadFile(); wrappers `api.ts:201-244` |
| `frontend/src/components/{ConfirmGate,GoogleSignInButton,SignUpScreen,SignInScreen,VerifyLanding,SignedInIndicator}.tsx` | Auth views + gate mirror | ✓ VERIFIED | ConfirmGate four-tier mirror (`ConfirmGate.tsx:59-87`); Google button self-guards |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `confirm.py` | `require_verified_user` (deps.py) | `Depends(require_verified_user)` gate on POST /api/confirm | ✓ WIRED | Signed-out → 401, unverified → 403 before any gate work |
| `confirm.py` | `service.confirm` → `build_manifest` | `confirmed_by=user.email` keyword arg | ✓ WIRED | Stamped into manifest.confirmed_by |
| `auth.py signup` | server console | `logger.info(... verify_url)` | ✓ WIRED | Verification link logged, password never logged |
| `app.py` | `SessionMiddleware` | conditional on `DATA_INGESTOR_GOOGLE_OAUTH == "1"` | ✓ WIRED | Off-by-default app starts with no extra middleware |
| frontend `api.ts` | backend auth routes | fetch with `credentials:'include'` | ✓ WIRED | Session cookie round-trips |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Auth-focused tests pass | `uv run pytest tests/api/test_confirm_auth_gate.py tests/api/test_google_oauth_flag.py tests/api/test_auth_routes.py tests/auth/ tests/api/test_auth_deps.py -q` | 45 passed | ✓ PASS |
| Full suite / no regressions | `uv run pytest -q` | 510 passed, 4 skipped (pre-existing live-test skips) | ✓ PASS |
| Signed-out confirm → 401 | `test_confirm_signed_out_returns_401_and_persists_nothing` | pass | ✓ PASS |
| Unverified confirm → 403 | `test_confirm_signed_in_unverified_returns_403_and_persists_nothing` | pass | ✓ PASS |
| Console verification link end-to-end | `test_verify_with_a_fresh_token_marks_the_user_verified` (token read from server log) | pass | ✓ PASS |
| Google flag off → 501 + no middleware | `test_google_login_returns_501_...`, `test_app_imports_and_starts_with_no_session_middleware_when_flag_off` | pass | ✓ PASS |
| confirmed_by stamped in manifest | `test_confirm_verified_user_records_confirmed_by_email_in_the_manifest` | pass | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| AUTH-01 | 06-01, 06-02, 06-03 | Account creation + sign-in; governed action requires signed-in (server-side gate) | ✓ SATISFIED | require_user/require_verified_user on /api/confirm; 401/403 tests |
| AUTH-02 | 06-02, 06-03 | Google OAuth behind off-by-default flag, placeholder creds | ✓ SATISFIED | google_oauth_enabled() + 501 routes + conditional middleware + null button |
| AUTH-03 | 06-01, 06-02, 06-03 | Email verification via console-printed link, no live provider | ✓ SATISFIED | signup logs verify link; e2e verify test drives it to verified |
| AUTH-04 | 06-02 | Manual confirm/edit attributed to signed-in user | ✓ SATISFIED | confirmed_by threaded to manifest from server-resolved User |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/assayingest/auth/sqlite_store.py` | 6 | word "placeholders" | ℹ️ Info | Refers to SQL parameterised `?` placeholders (a security note), not a stub |

No unreferenced TBD/FIXME/XXX debt markers in the phase's source files. Injection-scan `?token=` flags on auth.py and test_auth_routes.py are false positives (legitimate verification-link URLs).

### Human Verification Required

Four browser-only UI checks (deferred to end-of-phase per `human_verify_mode`). These do NOT block any success criterion — every criterion is independently verified server-side with passing tests — but the demo-visible frontend rendering/interaction can only be confirmed in a browser. See the `human_verification` frontmatter list: (1) sign-up console notice + VerifyLanding states, (2) the four ConfirmGate auth tiers + returnTo round-trip, (3) Google button absent when flag off, (4) AppShell identity chip + toasts + sign-out.

### Gaps Summary

No gaps. All four success criteria (AUTH-01/02/03/04) are achieved in the codebase and proven by passing behavioral tests: server-side 401 on signed-out confirm, 403 on unverified confirm, console-printed verification link consumed end-to-end, Google OAuth flag off-by-default returning 501 with no secret required, and `confirmed_by` threaded from the server-resolved user through `service.confirm` into `build_manifest`. Status is `human_needed` solely because the demo-visible frontend layer carries browser-only visual/interaction checks that were intentionally deferred to the end-of-phase human pass — not because any criterion is unmet.

---

_Verified: 2026-07-11_
_Verifier: Claude (gsd-verifier)_
