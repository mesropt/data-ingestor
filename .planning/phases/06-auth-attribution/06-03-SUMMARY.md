---
phase: 06-auth-attribution
plan: 03
subsystem: frontend-auth
tags: [react, vite, typescript, shadcn, auth, reducer, tdd, vitest, credentials-include]

# Dependency graph
requires:
  - phase: 06-02
    provides: "/api/auth/{signup,login,logout,verify,config,me} routes + flag-gated Google OAuth + di_session cookie + server-side require_verified_user gate on /api/confirm"
  - phase: 04-api-and-shell
    provides: "Vite+React shell (AppShell, ConfirmGate, Review), lib/api.ts request()/uploadFile()/ApiError, state/upload+review+fieldSet reducers, shadcn ui/* primitives"
provides:
  - "state/auth.ts: pure authReducer + isSignedIn/isVerified/isGovernedActionAllowed selectors"
  - "lib/api.ts: six typed auth wrappers (signUp/signIn/signOut/getMe/verifyEmail/getAuthConfig) + credentials:'include' on every fetch"
  - "Auth views: SignUpScreen, SignInScreen, VerifyLanding, GoogleSignInButton (conditional), AuthDivider, SignedInIndicator"
  - "AppShell identity chip + Sign Out; App mount-time session probe + /verify routing + auth-view overlay; ConfirmGate four-tier auth mirror"
affects: [07-schema-crud, alias-provenance, demo-video]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "credentials:'include' centralized in request() (shared) + added to uploadFile()'s bespoke fetch"
    - "auth store as a discriminated-union reducer with NO React import, mirroring state/upload.ts (logic tested, rendering gsd-ui-checker-validated)"
    - "returnTo carried on the auth state and preserved through SIGN_IN_SUCCESS for the redirected-from-Confirm round-trip"
    - "router-free /verify switch via a path state variable + history.pushState (no router dependency added)"
    - "ConfirmGate composes auth as two INDEPENDENT disable reasons ON TOP of the existing ready gate, never conflating copy"

key-files:
  created:
    - frontend/src/state/auth.ts
    - frontend/src/state/auth.test.ts
    - frontend/src/components/SignUpScreen.tsx
    - frontend/src/components/SignInScreen.tsx
    - frontend/src/components/VerifyLanding.tsx
    - frontend/src/components/GoogleSignInButton.tsx
    - frontend/src/components/AuthDivider.tsx
    - frontend/src/components/SignedInIndicator.tsx
  modified:
    - frontend/src/lib/types.ts
    - frontend/src/lib/api.ts
    - frontend/src/components/AppShell.tsx
    - frontend/src/components/ConfirmGate.tsx
    - frontend/src/screens/Review.tsx
    - frontend/src/App.tsx

decisions:
  - "Substituted lucide `Globe` for the UI-SPEC-named `Chrome` icon on the Google button — Chrome is no longer exported by the installed lucide-react; Globe keeps the Registry Safety FLAG intent (a generic placeholder, NOT a Google brand asset)"
  - "AppShell extended via a minimal optional `trailing` slot grouped with ThemeToggle (kept the header as three justify-between clusters) rather than restructuring the bar, preserving the load-bearing h-16/max-w-5xl geometry"
  - "Auth screens render as an in-shell overlay (replacing the tab body) reachable from the AppShell Sign In button and the ConfirmGate affordance; a tab click dismisses the overlay"
  - "signIn is called inside SignInScreen; success is handed to App via onSignedIn(user) which owns the store update + toast + overlay close + returnTo navigation"

# Metrics
duration: ~10 min
completed: 2026-07-11
status: complete

requirements-completed: [AUTH-01, AUTH-02, AUTH-03]
---

# Phase 6 Plan 3: Frontend Auth Surface Summary

**Added the demo-visible auth half of AUTH-01/02/03 on top of the shipped v1.0 React shell: a pure `authReducer` + selectors, six typed `api.ts` wrappers with `credentials:'include'` on every fetch, Sign Up / Sign In / Verify Landing views + a flag-conditional Google button, an AppShell identity chip with Sign Out, a mount-time session probe with router-free `/verify` routing, and a four-tier ConfirmGate auth mirror composed on top of (never replacing) the existing readiness gate — all from existing shadcn primitives/tokens, tsc + build clean, 73 vitest tests green.**

## Performance

- **Duration:** ~10 min (2026-07-11T13:52:23Z → 14:02:37Z)
- **Tasks:** 3 (Task 1 TDD: test → feat; Tasks 2-3: feat)
- **Files:** 14 (8 created, 6 modified)
- **Tests:** full vitest suite 73 passed (4 files); +17 new auth tests over the prior 56 baseline
- **Gates:** `npx tsc --noEmit` clean; `npm run build` succeeds; `npm run lint` clean on new files (3 pre-existing warnings in untouched `ui/*` primitives)

## Accomplishments

- **Task 1 — auth types, api wrappers, store (TDD).** `types.ts` gained `AuthUser` (mirrors `UserOut`: id/email/is_verified/auth_provider), `AuthConfig`, `SignUpBody`, `SignInBody`, `VerifyResult`, `SignUpAccepted` — each byte-matched to plan 06-02's Pydantic models (verified against `api/wire.py`). `api.ts` now sends `credentials:'include'` from the shared `request()` AND from `uploadFile()`'s bespoke `fetch`, and exposes `signUp`/`signIn`/`signOut`/`getMe`/`verifyEmail`/`getAuthConfig` reusing the existing `request`/`parseResponse`/`ApiError` idiom (a 401 from `getMe` surfaces as `ApiError` the probe treats as signed-out). `state/auth.ts` is a pure discriminated-union reducer (`probing | signedOut{returnTo?} | signedIn{user, returnTo?}`) with `isSignedIn`/`isVerified`/`isGovernedActionAllowed` selectors — no React import, mirroring `state/upload.ts`. RED (17 failing tests) → GREEN.
- **Task 2 — auth views.** `SignUpScreen` (centered `max-w-[420px]` Card, email + `new-password`, "Create Account" with a `Loader2` "Creating…" state; on success the card body is REPLACED by the amber `--uncertain*`-toned "Check your server console" notice + "Sign in now"; errors render the server's consequence-first message in a destructive Alert with field state preserved). `SignInScreen` (symmetric layout, clears only the password on bad creds, renders the muted "Sign in to confirm your mapping." line in the redirected-from-Confirm variant). `VerifyLanding` (reads `token` from the URL, calls `verifyEmail`, shows a `Loader2` then `MailCheck`/success-green "Email Verified" or a muted `Mail` "This link has expired"). `GoogleSignInButton` self-guards on `enabled` (returns `null` when off). `AuthDivider` renders the "or" row only alongside the Google button. No new token or registry component introduced.
- **Task 3 — shell, routing, gate mirror.** `SignedInIndicator` renders the signed-in `UserRound` + truncated mono email + icon-only Sign Out (Tooltip), the signed-out outline "Sign In", and a dimmed probing slot (never a blank gap). `AppShell` got a minimal `trailing` slot beside `ThemeToggle`. `App` introduces the auth store via `useReducer`, runs a mount-time `getAuthConfig()` + `getMe()` probe, routes `/verify?token=...` to `VerifyLanding` without a router dependency, and manages an `authView` overlay opened from both the AppShell button and the ConfirmGate affordance (with the returnTo round-trip and "Signed in as {email}." / "Signed out." toasts). `ConfirmGate` gained the four mutually-exclusive priority tiers (signed-out actionable outline "Sign In to Confirm" with `ShieldAlert` → unverified disabled with verify tooltip → not-ready unchanged → ready unchanged); `Review.tsx` threads `signedIn`/`verified`/`onRequireSignIn` through.

## Task Commits

1. Task 1 RED — `46e2b28` (test)
2. Task 1 GREEN — `ef878d1` (feat)
3. Task 2 — `af5dc2c` (feat)
4. Task 3 — `147caa3` (feat)

## Decisions Made

- **`Globe` instead of `Chrome`** for the Google button icon — the installed `lucide-react` no longer exports `Chrome`. `Globe` preserves the UI-SPEC Registry Safety FLAG's whole point (a generic placeholder, explicitly NOT Google's brand asset); the FLAG comment was updated to note the swap. See Deviations.
- **AppShell `trailing` slot** grouped with `ThemeToggle` (three justify-between clusters) rather than a 4th top-level child, so the `h-16`/`max-w-5xl` bar geometry — load-bearing for the ConfirmGate sticky math — is untouched.
- **Auth screens as an in-shell overlay** (replacing the tab body), reachable from the AppShell Sign In button and the ConfirmGate "Sign In to Confirm" affordance; a tab click dismisses it.

## Deviations from Plan

### 1. [Rule 3 - Blocking] Google-button icon: `Chrome` → `Globe`

- **Found during:** Task 2 (`npm run build`).
- **Issue:** The UI-SPEC and plan named the lucide `Chrome` icon for the Google button; this `lucide-react` version does not export `Chrome` (`TS2724`), failing the production build.
- **Fix:** Substituted `Globe`, an equivalent generic lucide icon, and updated the Registry Safety FLAG comment to record the swap. The FLAG's intent is unchanged — the icon is a placeholder, NOT a Google brand asset, and must be replaced with Google's real mark before any public flag-on demo (flag is off by default overnight).
- **Files modified:** frontend/src/components/GoogleSignInButton.tsx
- **Commit:** af5dc2c

## Threat Surface

Matches the plan's `<threat_model>` exactly — no new trust boundary introduced. The ConfirmGate auth mirror is UI-only (T-06-12: server `require_verified_user` re-checks every confirm); the frontend never reads or stores the HttpOnly `di_session` token, relying solely on `credentials:'include'` (T-06-13); the `isGovernedActionAllowed` selector reflects only the last server-resolved user, never an authoritative check (T-06-14); the Google button uses a documented generic placeholder icon and renders only when the backend reports the flag on (T-06-15, off by default). No stubs: `googleEnabled` defaults to `false` only until the mount probe resolves it from `/api/auth/config`.

## Verification

- `cd frontend && npx tsc --noEmit` — clean.
- `cd frontend && npm run build` — succeeds (2078 modules, dist emitted).
- `cd frontend && npx vitest run` — 73 passed (4 files), including the 17 new auth tests and all pre-existing state tests.
- `grep -c 'credentials: "include"' src/lib/api.ts` — non-zero (present on both `request()` and `uploadFile()`).
- The three `<human-check>` items (sign-up console notice + server-log link, verify landing, sign-in toast, absent Google button flag-off, the four ConfirmGate tiers) are deferred to the end-of-phase human verification pass per the plan (`human_verify_mode=end-of-phase`).

## Self-Check: PASSED

All 8 created files exist on disk; all 4 task commits (46e2b28, ef878d1, af5dc2c, 147caa3) present in git log. TDD gate for Task 1 satisfied (test `46e2b28` precedes feat `ef878d1`). tsc + build + 73-test suite all green.
