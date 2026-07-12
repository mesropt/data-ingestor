# Phase 6: Auth & Attribution - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning
**Mode:** Autonomous overnight build — decisions made by the orchestrator per the locked spec (memory `canonical-master-milestone.md`), not interactive discuss.

<domain>
## Phase Boundary

Add an authentication + session + identity layer to the *already-built* Phase 4 FastAPI app and React shell, so that every **governed action** requires a signed-in, named user:

- Creating or editing a **Schema** (built in Phase 07 — the endpoints do not exist yet, so this phase delivers the reusable `require_user` gate that Phase 07 will apply; it applies the gate now to the one governed endpoint that already exists: **confirm**).
- **Confirming a mapping** (the existing `/api/confirm` endpoint) is gated server-side.

The point of auth here is **governance/attribution**, not a feature wall: a manual mapping decision must be attributable to a specific person, because Phase 07's alias provenance (ALIAS-03) records *which user* set a `manual` alias. So this phase must make the authenticated user's identity **available to the confirm/edit path** for downstream provenance stamping.

The build must stay **runnable overnight without live provider secrets**: email verification prints its link to the server console; Google OAuth ships behind a feature flag that is **off by default** with placeholder credentials. Wiring live Google OAuth client id/secret and a real email provider is the **user's own follow-up**, explicitly out of scope.

Requirements: AUTH-01, AUTH-02, AUTH-03, AUTH-04.

Out of scope: Organizations / multi-tenancy (FUTURE); roles/permissions beyond "signed in" (FUTURE); real email delivery; live Google OAuth credentials; password reset flow (nice-to-have, not required by AUTH-01..04 — defer unless trivial); the Schema CRUD endpoints themselves (Phase 07 builds them and applies this phase's gate).
</domain>

<binding_principles>
## Binding Principles (carry forward — still govern)

**P1 — Server-side enforcement, never UI-only (lives-at-stake heritage).** The governed-action gate is enforced on the **endpoint** via a FastAPI dependency, exactly as the Phase 4 confirm/export gate is re-checked server-side. A hidden button in the UI is a UX convenience that MIRRORS the server gate, never replaces it. Signed-out requests to a governed endpoint get `401`, regardless of what the client renders.

**P2 — Confidentiality & local-first.** The user store stays **local SQLite on the server host** (same DB/pattern as the profile + field-set stores, behind the existing `deps.py` DI seam) — never a network DB in v2.0. Passwords are never stored in plaintext (hashed with a modern KDF). Session cookies are `HttpOnly` + `SameSite=Lax` so the token is not reachable from JS.

**P3 — Overnight-runnable without secrets.** No step may hard-require a real Google client secret or SMTP server. Email verification link → server console. Google OAuth → feature flag off by default with placeholder env vars. The whole end-to-end flow (sign up → verify via console link → sign in → confirm a mapping) must pass in tests and a live run with zero external provider setup.
</binding_principles>

<decisions>
## Implementation Decisions (orchestrator's calls — planner may refine within these)

### D-06-01 — Session mechanism: signed HttpOnly cookie
Use a **stateless signed session cookie** (`HttpOnly`, `SameSite=Lax`, `Secure` when not localhost) carrying the user id, signed server-side (itsdangerous / Starlette `SessionMiddleware`, or a short JWT in the cookie — planner's exact lib call). Rationale: no server-side session table to manage, works same-origin with the Phase 4 single-process deployment, and the Phase 4 dev CORS already sets `allow_credentials=True`. A server-side session table is acceptable if the planner prefers it, but the cookie MUST stay `HttpOnly`.

### D-06-02 — User store extends the existing local SQLite behind the DI seam
Add a `users` table to the **same SQLite database** the profile/field-set stores use, exposed through a new repository (`UserStore`) injected via a `deps.py` `get_user_store()` function — mirroring `get_profile_store()` / `get_field_set_store()`. Tests override it with a tmp-path store; no test touches the real demo DB. Clean-Architecture boundary: a pure-Python `User` domain model, wire models stay at the API edge.

### D-06-03 — Password hashing with a modern KDF
Hash passwords with **bcrypt or argon2** (via `passlib` or `argon2-cffi` / `bcrypt` — planner picks one and adds the dep). Never store or log plaintext. Basic strength rule: minimum length (e.g. ≥ 8); do not over-engineer policy (ASVS L1).

### D-06-04 — Email verification: console-printed link (dev fallback)
On sign-up, mint a single-use, expiring verification token; **print the full verification URL to the server console** (via the app logger / stdout) instead of emailing it. A `GET/POST /api/auth/verify` endpoint consumes the token and marks the user verified. Decision on whether an unverified user may sign in but not perform governed actions vs cannot sign in at all: **allow sign-in but block governed actions until verified** (keeps the demo smooth while still exercising verification) — planner may flip to "must verify before sign-in" if cleaner, but AUTH-03's console-link completion must be demonstrable.

### D-06-05 — Google OAuth behind an off-by-default feature flag
Implement the OAuth authorization-code route(s) (`/api/auth/google/login` → redirect, `/api/auth/google/callback`) using a standard lib (**Authlib** preferred). Gate the whole path behind an env flag (e.g. `DATA_INGESTOR_GOOGLE_OAUTH=1`, default off) reading placeholder `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` from env. When the flag is off: the routes return a clear `501/404` and the frontend hides or disables the "Sign in with Google" button. Add the placeholder vars to `.env.example`. No live secret is committed or required.

### D-06-06 — The gate is a reusable dependency; identity threads into confirm
Provide `require_user` (FastAPI `Depends`) returning the authenticated `User`; apply it now to `/api/confirm` (AUTH-01 server-side). Thread the user's identity (email/id) into the confirm service call so it is **available to stamp provenance** — Phase 07 consumes it for ALIAS-03/04. Phase 06's job is to make identity *present and recorded at the confirm boundary*, not to build the crosswalk. A lightweight record (e.g. `confirmed_by` on whatever the confirm path persists, or simply passing it through to be returned) satisfies AUTH-04; do not over-build.

### D-06-07 — Frontend auth surface
Add: a small auth store/context, a **Sign up** and **Sign in** view, an "check the server console for your verification link" notice after sign-up, the current-signed-in-user indicator + sign-out in the AppShell, and a Google button that only shows when the backend reports the OAuth flag is on (expose flag state via a tiny `/api/auth/config` or the existing config surface). The **Confirm & Save** action is disabled/redirects to sign-in when signed out (mirrors the server gate). Keep the existing shadcn / `data-theme` dark aesthetic; this is still demo-visible, so the auth views should look consistent, not bolted on.

### Claude's Discretion (planner / ui-researcher decide)
- Exact session lib (Starlette SessionMiddleware vs itsdangerous vs JWT-in-cookie) and cookie max-age.
- Exact users table columns beyond the essentials (id, email, password_hash, is_verified, created_at, auth_provider).
- Whether verification token lives in the users table or its own table.
- Route module layout under `api/routes/auth.py` (likely one new router) and wire-model shapes.
- React auth state approach (context + hook vs a store file like the existing `state/` modules) and routing for the auth views.
- Whether to add a minimal `password reset` — only if trivial; not required.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 4 API foundations this phase extends (do NOT reimplement)
- `src/assayingest/api/app.py` — FastAPI app, router includes, dev CORS (`allow_credentials=True` already set), `app.frontend()` static mount. The new auth router registers here.
- `src/assayingest/api/deps.py` — the DI seam pattern (`get_profile_store`, `get_field_set_store`, `get_anthropic_client`). Add `get_user_store()` and the session/current-user dependency here in the same style.
- `src/assayingest/api/routes/confirm.py` — the existing governed endpoint to gate with `require_user`; this is where identity must thread in for AUTH-04.
- `src/assayingest/api/wire.py` — wire models live here; add auth request/response models at this boundary.
- `src/assayingest/api/state.py` — existing per-request/app state handling.
- `src/assayingest/service.py` — `confirm()` and related orchestration; the identity is threaded through here (kept print/transport-decoupled per Phase 4).
- `src/assayingest/learning/store.py` + `sqlite_store.py` + `sqlite_field_set_store.py` — the repository seam + SQLite connection pattern the new `UserStore` mirrors (same DB file / path resolution).
- `src/assayingest/domain/models.py` — where a pure-Python `User` domain model belongs (frozen dataclass style).

### Frontend foundations to extend
- `frontend/src/components/AppShell.tsx` — add the signed-in-user indicator + sign-out.
- `frontend/src/components/ConfirmGate.tsx` / `ExportBar.tsx` — the confirm action to gate behind sign-in in the UI (mirror only).
- `frontend/src/lib/api.ts` — the fetch layer; auth calls + `credentials: 'include'` go here.
- `frontend/src/state/` — existing store-module idiom (`upload.ts`, `review.ts`, `fieldSet.ts`) for an auth store.
- `frontend/src/components/ui/*` — existing shadcn primitives (input, button, label, card) for the auth forms.

### Config / secrets
- `.env.example` — add `DATA_INGESTOR_GOOGLE_OAUTH`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and a `SESSION_SECRET` placeholder. Never commit real values. (Live `.env` is gitignored.)
</canonical_refs>

<success_criteria>
## Success Criteria (from ROADMAP — what must be TRUE)

1. **AUTH-01** — A visitor can create an account and sign in; attempting to create/edit a Schema or confirm a mapping while signed out is blocked and prompts sign-in — the gate is enforced **server-side on the endpoint**, not only hidden in the UI.
2. **AUTH-03** — A user can request email verification and complete it by following the link the dev build **prints to the server console** — no live email provider required.
3. **AUTH-02** — A "Sign in with Google" path exists behind a **feature flag off by default** with placeholder credentials, so the overnight build runs end-to-end without live OAuth secrets.
4. **AUTH-04** — When a signed-in user confirms a mapping or edits a field mapping, their **identity is recorded and available** to stamp onto alias provenance downstream.
</success_criteria>
