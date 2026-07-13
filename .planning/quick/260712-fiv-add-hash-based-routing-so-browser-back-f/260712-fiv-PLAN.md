---
phase: quick-260712-fiv
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/state/routing.ts
  - frontend/src/state/routing.test.ts
  - frontend/src/App.tsx
autonomous: true
requirements: []
must_haves:
  truths:
    - "Clicking a tab changes the URL to that tab's hash (#upload, #review, ...)."
    - "Browser Back after switching tabs returns to the previous tab instead of leaving the app."
    - "Reloading (F5) on #registry re-opens the Registry tab, not the first tab."
    - "An unknown, empty, or garbage hash resolves to the default tab (define-fields) — never a blank screen."
    - "Deep-linking #review with no upload in session shows Review's existing 'No file uploaded yet.' empty state."
    - "The /verify?token=... path landing still renders, unaffected by hash routing."
  artifacts:
    - frontend/src/state/routing.ts
    - frontend/src/state/routing.test.ts
  key_links:
    - "App.tsx TABS (the only slug source) -> TAB_VALUES -> tabFromHash allowlist"
    - "window 'hashchange' listener -> setActiveTab (this is what makes Back/Forward work)"
    - "every activeTab write goes through one navigateTo() so state and hash never diverge"
---

<objective>
Sync `activeTab` with `location.hash` so the five tabs become linkable, bookmarkable, refresh-stable, and reachable via browser Back/Forward — with no router dependency.

Purpose: today the URL is always `/`. Back leaves the app entirely; F5 dumps the user back on `define-fields`. That is a real usability defect on a demo the judges will click around in.
Output: a pure, node-testable `state/routing.ts` (hash <-> tab), its vitest spec, and thin `window` wiring in `App.tsx`.
</objective>

<context>
@.planning/STATE.md
@frontend/src/App.tsx
@frontend/src/state/upload.ts
@frontend/src/state/upload.test.ts
</context>

<facts>
Verified during planning — do not re-derive:
- `TABS` (`App.tsx:19-25`) is the single source of truth for the five slugs: `define-fields`, `upload`, `review`, `registry`, `docs`. `TABS[0].value` is today's default. Derive the allowlist FROM it; never hand-copy the list into `state/`.
- `App.tsx:44-48` keeps a router-free PATH switch (`path` / `setPath`, rendering `VerifyLanding` on `/verify`). Hash routing is orthogonal. Leave the path switch byte-for-byte alone.
- `Review.tsx:82-91` already renders a real empty state ("No file uploaded yet.") when `mapping`/`fieldSet` is null. Deep-linking `#review` cold therefore degrades gracefully with NO redirect and NO fallback logic. Do not add one.
- `activeTab` is currently written in three places: `handleMapped` (`App.tsx:72`), `handleTabChange` (`App.tsx:78`), `handleSignedIn` (`App.tsx:87`). All three must go through the new single navigation helper, or state and URL will silently diverge.
- `frontend/vite.config.ts:24-27` sets vitest `environment: 'node'` — there is NO DOM. Pure functions must therefore take the hash as a plain `string` argument and must never touch `window`. Do not add jsdom; do not change the environment.
- `tsconfig.app.json` enables `noUnusedLocals`/`noUnusedParameters` — an orphaned import fails `npm run build`.
- `package.json` `test` script is bare `vitest` (watch mode); CI-style runs need `-- --run`.
</facts>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Pure hash &lt;-&gt; tab functions (RED then GREEN)</name>
  <files>frontend/src/state/routing.ts, frontend/src/state/routing.test.ts</files>
  <behavior>
    Write `routing.test.ts` FIRST and watch it fail (module does not exist), mirroring how `state/upload.test.ts` covers `state/upload.ts` — pure logic, no rendering, no `window`.

    `tabFromHash(hash: string, tabs: readonly string[]): string`
    - "#upload" + full slug list -> "upload"
    - "upload" (no leading '#') -> "upload"  (a caller may pass either form)
    - "#define-fields" -> "define-fields" (hyphenated slug survives)
    - "#nonsense" -> "define-fields" (unknown -> first tab)
    - "#" -> "define-fields"
    - "" -> "define-fields"
    - "#/review" -> "review" (a stray leading slash is tolerated, not a 404)
    - "#UPLOAD" -> "upload" (hand-typed hashes vary in case; the real slugs are all lowercase)
    - "#%20upload" / other percent-encoded junk -> "define-fields" (fails the allowlist, so it degrades to default rather than throwing)
    - Guard property: the return value is ALWAYS a member of the `tabs` argument, for every input above. This is the property that makes a blank screen impossible.

    `hashForTab(tab: string): string`
    - "review" -> "#review"

    Round-trip property test: for EVERY slug in the list, `tabFromHash(hashForTab(slug), slugs) === slug`.

    Test fixture: declare the five slugs as local test DATA inside the spec (e.g. `const TAB_SLUGS = ["define-fields", "upload", "review", "registry", "docs"]`). This is not a duplicate source of truth — production code receives the list as an argument from `App.tsx`'s `TABS`, so there is exactly one live copy; the spec merely feeds the pure function representative input.
  </behavior>
  <action>
    Create `frontend/src/state/routing.ts` exporting exactly the two functions above.

    `tabFromHash` normalizes then allowlists — in that order, as two levels of abstraction: a small private normalizer (trim, strip a leading '#', strip a leading '/', lowercase) and the public function that returns the slug only if `tabs.includes(...)`, else `tabs[0]`. The allowlist is the whole safety story: an unrecognized hash can only ever produce the default tab, so no hash value can render an unknown screen.

    `hashForTab` is the trivial inverse and exists so `App.tsx` never string-concatenates a '#' by hand.

    Per CLAUDE.md, document WHY, not WHAT: the module docstring should state that these are pure and `window`-free precisely because vitest runs in `environment: 'node'` (no DOM), so the `window` wiring stays in `App.tsx` as the untested seam. Note in the code that `tabs[0]` is the default by convention, matching `App.tsx`'s existing `useState(TABS[0].value)`.

    Do NOT add any dependency. Do NOT export a hardcoded slug list from this module — the caller supplies it.
  </action>
  <verify>
    <automated>cd frontend &amp;&amp; npx vitest run src/state/routing.test.ts</automated>
  </verify>
  <done>`routing.test.ts` failed before `routing.ts` existed (RED observed and reported), and now every case above passes. No `window` reference in `routing.ts`.</done>
</task>

<task type="auto">
  <name>Task 2: Wire the hash into App.tsx (mount read, tab write, hashchange listener)</name>
  <files>frontend/src/App.tsx</files>
  <action>
    Import `hashForTab` / `tabFromHash` from `@/state/routing` and derive the allowlist from the existing `TABS` const — add a module-level `const TAB_VALUES = TABS.map((tab) => tab.value);` right below `TABS`. `TABS` stays the single source of truth; nothing else may list the slugs.

    1. Seed from the URL: change `useState<string>(TABS[0].value)` (line 36) to a lazy initializer that reads the hash — guarding `typeof window === "undefined"` exactly the way the neighbouring `path` state at line 46 already does, and passing `TAB_VALUES` so an unknown hash lands on the default.

    2. Add ONE navigation helper, `navigateTo(tab: string)`, that is the only writer of `activeTab`: it clears `authView` (leaving a tab also dismisses an open auth overlay — the behaviour `handleTabChange` has today), sets `activeTab`, and assigns `window.location.hash = hashForTab(tab)`. Assigning the hash (rather than `history.replaceState`) is deliberate: it pushes a history entry, which is the mechanism that gives the user a working Back button. Route all three existing writers through it — `handleMapped` (line 72), `handleTabChange` (line 75-79), `handleSignedIn` (line 87).

    3. Add a `useEffect` with an empty dep array that subscribes to `window`'s `hashchange` and, on each event, applies `tabFromHash(window.location.hash, TAB_VALUES)` via the same clear-overlay-then-set-tab path — and returns a cleanup that removes the listener. This effect is what makes Back/Forward move between tabs; without it the URL would change and the screen would not. It must also clear `authView`, otherwise pressing Back while the sign-in overlay is open would swap the tab underneath a still-covering overlay.

    Deliberate non-goals, so the diff stays honest:
    - Do NOT rewrite a garbage hash in the URL on mount. Doing so would also stamp a hash onto the `/verify?token=...` landing (whose hooks still run before that early return), and the allowlist already guarantees a correct screen. The URL self-corrects the moment the user clicks any tab.
    - Do NOT touch the `path`/`setPath`/`goToApp` verification-landing switch or the `Review` `key={lastMapping?.upload_token ?? "empty"}` line.
    - Do NOT add a redirect for a cold `#review` — `Review` already renders its own empty state.

    Setting `window.location.hash` inside `navigateTo` re-fires `hashchange`, whose handler recomputes the same tab — a harmless idempotent no-op, not a loop. Say so in a comment so the next reader does not "fix" it.
  </action>
  <verify>
    <automated>cd frontend &amp;&amp; npm run test -- --run &amp;&amp; npm run build &amp;&amp; git diff --stat package.json</automated>
  </verify>
  <done>
    Full vitest suite green — the 124 pre-existing tests still pass, plus Task 1's new ones (report the REAL total). `npm run build` (tsc -b &amp;&amp; vite build) typechecks and bundles clean. `git diff --stat frontend/package.json` is empty, proving no dependency was added. `activeTab` is assigned in exactly one function (`navigateTo`) plus the mount initializer and the `hashchange` handler.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| URL bar -> client state | `location.hash` is fully attacker/user-controlled text entering the app |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-fiv-01 | Tampering | `tabFromHash` | low | mitigate | The hash is matched against the `TAB_VALUES` allowlist and is never rendered, never used as markup, and never used to build a request URL. A non-member returns `tabs[0]`, so a hostile hash can only ever select an existing screen. |
| T-fiv-02 | Information disclosure | hash in history/referrer | low | accept | Only opaque tab slugs are written to the hash — no upload token, no mapping, no email. Nothing sensitive enters the URL. |

No package installs in this task, so no supply-chain (`T-*-SC`) surface.
</threat_model>

<verification>
Run from the repo root, and report REAL output (not a summary) for both gates:

1. `cd frontend && npm run test -- --run` — vitest; 124 tests pass today, so the count must only go UP and nothing may regress.
2. `cd frontend && npm run build` — `tsc -b && vite build`; must typecheck clean.

Manual smoke (the dev server on :8000 already serves `frontend/dist` from disk, so the `npm run build` above is enough to publish the change — do NOT kill it, do NOT start a second server on :8000):
- Click Upload -> URL shows `#upload`. Click Review -> `#review`. Press Back -> returns to Upload (not out of the app).
- Load `http://localhost:8000/#registry` fresh -> Registry tab is open.
- Load `http://localhost:8000/#nonsense` -> Define Fields renders (no blank screen).
- Load `http://localhost:8000/#review` cold -> "No file uploaded yet." empty state.
- `/verify?token=...` still renders the verification landing.
</verification>

<success_criteria>
- Tabs are linkable, bookmarkable, and refresh-stable; Back/Forward move between them.
- Garbage/empty hash always resolves to `define-fields`.
- Hash<->tab logic is pure and unit-tested in `state/routing.ts`; only thin `window` wiring lives in `App.tsx`.
- Zero new dependencies; vitest still runs in `environment: 'node'`.
- Commit message: English, capitalized, one short imperative line (&le;150 chars), e.g. `Add hash-based routing so tabs are linkable and Back/Forward work`.
</success_criteria>

<output>
Create `.planning/quick/260712-fiv-add-hash-based-routing-so-browser-back-f/260712-fiv-SUMMARY.md` when done.
</output>
